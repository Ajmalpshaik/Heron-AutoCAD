"""Long AutoLISP is cut between its top-level forms, never inside one (#46).

AutoCAD drops command-line text near 3,600 characters without a word (known
limit 3), so autocad_run_lisp used to refuse anything over 2,000. Now the code
is cut between its top-level forms into pieces under about 700 characters,
sent in order inside one undo mark. A single form that is itself too long is
refused, never cut.
"""

from __future__ import annotations

import asyncio
import json
import re

import pytest
import pythoncom

from autocad_mcp.acad.lisp_forms import (
    CHUNK_CHARS,
    FORM_MAX_CHARS,
    LispTextError,
    chunk_forms,
    split_forms,
)
from autocad_mcp.tools import advanced
from autocad_mcp.tools.advanced import (
    LISP_CANCELLED_VAR,
    LISP_RESULT_VAR,
    LISP_SENTINEL,
)

BUSY = pythoncom.com_error(-2147418111, "Call was rejected by callee.", None, None)


def defun(name: str, body_chars: int) -> str:
    """A defun of about body_chars characters, with comments and line breaks in it."""
    body = " ".join(f'(setq v{i} "x")' for i in range(body_chars // 14))
    return f"(defun {name} ( / v)\n  ; set them all\n  {body}\n)"


class TestSplitForms:
    def test_each_top_level_form_comes_back_whole_and_in_order(self):
        assert split_forms("(setq a 1) (setq b 2)\n(+ a b)") == ["(setq a 1)", "(setq b 2)", "(+ a b)"]

    def test_a_nested_form_is_never_cut(self):
        assert split_forms('(defun f () (if (> a 1) (princ "big") (princ "small")))') == [
            '(defun f () (if (> a 1) (princ "big") (princ "small")))'
        ]

    def test_comments_go_and_spaces_close_up(self):
        text = "; a routine\n(defun f ()\n    ; inside\n    (princ)   ;| block |; (princ))"
        assert split_forms(text) == ["(defun f () (princ) (princ))"]

    def test_strings_are_kept_exactly_brackets_semicolons_and_spaces_too(self):
        text = '(princ "a ( b ; c   d \\" e )")'
        assert split_forms(text) == [text]

    def test_a_quote_inside_a_form_is_kept(self):
        assert split_forms("(setq l '(1 2 3))") == ["(setq l '(1 2 3))"]

    @pytest.mark.parametrize(
        "text, words",
        [
            ("(setq a 1", "never closed"),
            ("(setq a 1))", "closes nothing"),
            ('(princ "open)', "double quotes"),
            ("(setq a 1) b", "outside any"),
            ("'(1 2)", "outside any"),
            ("(princ) ;| never closed", "never closed with |;"),
            ("; only a comment", "no AutoLISP form"),
        ],
    )
    def test_text_that_is_not_whole_forms_is_refused(self, text, words):
        with pytest.raises(LispTextError, match=re.escape(words)):
            split_forms(text)


class TestChunkForms:
    def test_short_forms_share_a_piece_inside_progn(self):
        assert chunk_forms(["(setq a 1)", "(setq b 2)"]) == ["(progn (setq a 1) (setq b 2))"]

    def test_one_form_is_sent_as_it_is(self):
        assert chunk_forms(["(+ 1 2)"]) == ["(+ 1 2)"]

    def test_every_piece_stays_under_the_limit_and_the_forms_stay_in_order(self):
        forms = [f"(setq a{i} {i})" for i in range(300)]
        chunks = chunk_forms(forms)
        assert len(chunks) > 1
        assert all(len(c) <= CHUNK_CHARS for c in chunks)
        assert " ".join(chunks).count("(setq") == 300
        joined = re.findall(r"\(setq a(\d+)", " ".join(chunks))
        assert [int(n) for n in joined] == list(range(300))

    def test_a_form_over_the_limit_but_not_too_long_goes_alone(self):
        big = "(+ " + "1 " * 500 + ")"
        assert CHUNK_CHARS < len(big) <= FORM_MAX_CHARS
        assert chunk_forms(["(setq a 1)", big, "(setq b 2)"]) == ["(setq a 1)", big, "(setq b 2)"]

    def test_a_single_form_that_is_too_long_is_refused_never_cut(self):
        huge = "(+ " + "1 " * 1100 + ")"
        with pytest.raises(LispTextError) as err:
            chunk_forms(["(setq a 1)", huge])
        assert "Form 2 of 2" in str(err.value)
        assert "Split it" in str(err.value)

    def test_a_long_routine_of_defuns_is_cut_between_the_defuns(self):
        text = "\n".join(defun(f"f{i}", 600) for i in range(6))
        assert len(text) > 3600
        chunks = chunk_forms(split_forms(text))
        assert len(chunks) == 6
        assert all(c.startswith("(defun f") for c in chunks)


class Doc:
    """Runs each piece the way AutoCAD would: one result per piece, or a timeout, a cancel or a refusal."""

    def __init__(self, timeout_at=None, cancel_at=None, refuse_at=None, busy_at=None):
        self.variables = {LISP_RESULT_VAR: "mine", LISP_CANCELLED_VAR: "also mine", "OSMODE": 675, "CMDACTIVE": 0}
        self.sent: list[str] = []
        self.timeout_at, self.cancel_at, self.refuse_at, self.busy_at = timeout_at, cancel_at, refuse_at, busy_at
        self.marks: list[str] = []

    def GetVariable(self, name):
        return self.variables[name]

    def SetVariable(self, name, value):
        self.variables[name] = value

    def SendCommand(self, text):
        self.sent.append(text)
        number = len(self.sent)
        if number == self.refuse_at:
            raise RuntimeError("bad LISP")
        if number == self.busy_at:
            raise BUSY
        if number == self.timeout_at:
            return
        self.variables[LISP_CANCELLED_VAR] = "LINE" if number == self.cancel_at else ""
        self.variables[LISP_RESULT_VAR] = f"value {number}"

    def StartUndoMark(self):
        self.marks.append("start")

    def EndUndoMark(self):
        self.marks.append("end")


@pytest.fixture
def lisp(monkeypatch):
    holder: dict[str, Doc] = {}

    async def run(fn):
        return fn()

    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    monkeypatch.setattr(advanced, "run", run)
    monkeypatch.setattr(advanced, "time", Clock())
    monkeypatch.setattr(advanced, "LISP_POLL_ATTEMPTS", 3)
    monkeypatch.setattr(advanced, "get_doc", lambda: holder["doc"])
    monkeypatch.setattr(advanced, "require_idle", lambda d: None)

    def call(expression: str, doc: Doc | None = None) -> tuple[str, Doc]:
        holder["doc"] = doc or Doc()
        return asyncio.run(advanced.autocad_run_lisp(expression=expression)), holder["doc"]

    return call


LONG = "\n".join(defun(f"f{i}", 600) for i in range(6)) + "\n(f5)"


class TestRunLispInPieces:
    def test_long_code_is_sent_in_pieces_in_order_inside_one_undo_mark(self, lisp):
        text, doc = lisp(LONG)
        answer = json.loads(text)
        assert answer["chunks"] == len(doc.sent) == 6  # one defun a piece; the call shares the last
        assert answer["chunks_finished"] == 6
        assert answer["result"] == "value 6"
        assert doc.marks == ["start", "end"]  # one undo step for the whole call
        assert all("(defun f" in sent for sent in doc.sent)
        assert "(progn (defun f5" in doc.sent[5] and "(f5))" in doc.sent[5]

    def test_every_piece_sent_stays_far_under_what_autocad_drops(self, lisp):
        _, doc = lisp(LONG)
        assert all(len(sent) < 1300 for sent in doc.sent)  # 700 of code + the wrapper (about 500, #157)

    def test_several_short_forms_are_one_progn_and_give_the_last_value(self, lisp):
        text, doc = lisp("(setq a 1) (setq b 2)")
        answer = json.loads(text)
        assert len(doc.sent) == 1
        assert "(progn (setq a 1) (setq b 2))" in doc.sent[0]
        assert answer["result"] == "value 1"
        assert "chunks" not in answer  # one piece: the answer reads as before

    def test_a_piece_that_times_out_stops_the_rest_and_says_which(self, lisp):
        text, doc = lisp(LONG, Doc(timeout_at=3))
        answer = json.loads(text)
        assert len(doc.sent) == 3
        assert answer["timed_out"] is True
        assert answer["chunks_finished"] == 2
        assert "piece 3 of 6" in answer["note"]
        assert "3 more were not sent" in answer["note"]

    def test_a_command_left_open_in_a_piece_stops_the_rest(self, lisp):
        text, doc = lisp(LONG, Doc(cancel_at=2))
        answer = json.loads(text)
        assert len(doc.sent) == 2
        assert answer["cancelled_command"] == "LINE"
        assert "piece 2 of 6" in answer["note"]

    def test_a_refused_piece_says_what_had_already_run(self, lisp):
        text, doc = lisp(LONG, Doc(refuse_at=4))
        # Part of the code ran, so it is never "refused, nothing changed" (review of PR #149).
        assert text.startswith("Error: Outcome unknown: AutoCAD refused piece 4 of 6")
        assert "Pieces 1 to 3 of 6 had already run" in text
        assert len(doc.sent) == 4
        assert doc.variables["OSMODE"] == 675
        assert doc.variables[LISP_RESULT_VAR] == "mine"  # put back even though it failed

    def test_a_busy_autocad_as_a_piece_is_sent_is_outcome_unknown_never_a_second_send(self, lisp):
        text, doc = lisp(LONG, Doc(busy_at=2))
        assert text.startswith("Error: Outcome unknown")
        assert "Piece 1 of 6 had already run" in text
        assert len(doc.sent) == 2

    def test_one_form_too_long_is_refused_and_nothing_is_sent(self, lisp):
        huge = "(progn " + "(+ 1 2) " * 300 + ")"
        text, doc = lisp(f"(setq a 1) {huge}")
        assert text.startswith("Error")
        assert "Form 2 of 2" in text and "Nothing was sent" in text
        assert doc.sent == []

    def test_more_than_one_call_takes_is_refused(self, lisp):
        text, doc = lisp("(setq a 1) " * (advanced.LISP_MAX_TOTAL // 11 + 2))
        assert text.startswith("Error") and "at most" in text
        assert doc.sent == []

    def test_brackets_inside_a_string_no_longer_count(self, lisp):
        text, doc = lisp('(princ "(")')
        assert not text.startswith("Error"), text
        assert '(princ "(")' in doc.sent[0]

    def test_a_save_hidden_in_a_later_piece_is_still_refused(self, lisp):
        text, doc = lisp(LONG + '\n(command "_.QSAVE")')
        assert text.startswith("Error") and "Publish padlock" in text
        assert doc.sent == []

    def test_a_short_expression_is_sent_as_before(self, lisp):
        text, doc = lisp("(* 6 7)")
        assert json.loads(text)["expression"] == "(* 6 7)"
        assert doc.sent == [advanced.lisp_wrapper("(* 6 7)")]
        assert LISP_SENTINEL not in doc.variables.values()


class TestReviewFindings:
    """Found by an independent review of PR #149."""

    @pytest.mark.parametrize("comment", ['; say "hi', ';| don\'t "x |;'])
    def test_a_quote_inside_a_comment_cannot_hide_a_save(self, lisp, comment):
        text, doc = lisp(f'(princ) {comment}\n(command "_.QSAVE")')
        assert text.startswith("Error") and "Publish padlock" in text
        assert doc.sent == []

    def test_the_first_piece_refused_is_still_a_plain_refusal(self, lisp):
        text, doc = lisp(LONG, Doc(refuse_at=1))
        assert text.startswith("Error: AutoCAD refused the expression")
        assert "had already run" not in text

    def test_a_run_stopped_part_way_never_reads_done(self, lisp):
        from autocad_mcp.core import answers

        text, _ = lisp(LONG, Doc(cancel_at=2))
        facts = answers.Facts(text, ok=True, outcome="done", counted={"added": 0, "modified": 0, "erased": 0},
                              wrote=True, can_count=False)
        line = answers.line(facts)
        assert line.startswith("OUTCOME UNKNOWN - the code stopped at piece 3 of 6; the pieces before it ran")
