"""PDF Import (#113, D-106): -PDFIMPORT typed with every answer in one form, never left open.

There is no AutoCAD here, so these pin what is sent and what is read back: the
release check, the refusals before anything is sent, the variables set for the
call and put back, the order of the answers, a command left open cancelled and
the pieces after it never sent, and the report of what came in. Whether
AutoCAD 2021-2027 asks exactly these questions is Group AO in NEEDS-CHECKING.
"""

from __future__ import annotations

import asyncio
import json
import zlib

import pytest

from autocad_mcp.acad import pdf_import as pdf
from autocad_mcp.acad.lisp_forms import CHUNK_CHARS, FORM_MAX_CHARS, split_forms
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import advanced
from autocad_mcp.tools import pdf_import as tool
from autocad_mcp.tools.advanced import LISP_CANCELLED_VAR, LISP_RESULT_VAR, lisp_wrapper


def write_pdf(folder, name="vendor.pdf", pages=2, compressed=False, encrypted=False) -> str:
    """A small file that looks like a PDF to Heron's checks (AutoCAD never reads it here)."""
    kids = " ".join(f"{n + 3} 0 R" for n in range(pages))
    tree = f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode()
    body = b"%PDF-1.7\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
    if compressed:
        packed = zlib.compress(b"2 0 " + tree)
        body += b"5 0 obj << /Type /ObjStm /Filter /FlateDecode >> stream\n" + packed + b"\nendstream endobj\n"
    else:
        body += b"2 0 obj " + tree + b" endobj\n"
    for n in range(pages):
        body += f"{n + 3} 0 obj << /Type /Page /Parent 2 0 R >> endobj\n".encode()
    if encrypted:
        body += b"trailer << /Encrypt 9 0 R >>\n"
    target = folder / name
    target.write_bytes(body + b"%%EOF\n")
    return str(target)


# ---- the parts that need no AutoCAD ------------------------------------------------------


class TestRelease:
    @pytest.mark.parametrize(("acadver", "year"), [
        ("24.0s (LMS Tech)", 2021), ("24.3s (LMS Tech)", 2024), ("25.1s (LMS Tech)", 2026), ("26.0s (LMS Tech)", 2027),
    ])
    def test_the_listed_releases_are_known(self, acadver, year):
        assert pdf.release_year(acadver) == year

    @pytest.mark.parametrize("acadver", ["23.1s (LMS Tech)", "27.0s", "", "garbage"])
    def test_any_other_release_is_refused_rather_than_answered_blind(self, acadver):
        with pytest.raises(ValueError, match="nothing was sent"):
            pdf.release_year(acadver)


class TestFile:
    def test_a_missing_file_is_refused(self, tmp_path):
        with pytest.raises(ValueError, match="No file exists"):
            pdf.pdf_file(str(tmp_path / "missing.pdf"))

    def test_a_drawing_is_sent_to_the_xref_tools(self, tmp_path):
        with pytest.raises(ValueError, match="attach_xref"):
            pdf.pdf_file(str(tmp_path / "plan.dwg"))

    def test_a_file_named_pdf_that_is_not_one_is_refused(self, tmp_path):
        fake = tmp_path / "scan.pdf"
        fake.write_bytes(b"PK\x03\x04 this is a zip")
        with pytest.raises(ValueError, match="not a PDF inside"):
            pdf.pdf_file(str(fake))

    def test_a_real_one_comes_back_whole_and_quotes_are_dropped(self, tmp_path):
        made = write_pdf(tmp_path, "AHU 01 GA.pdf")
        assert pdf.pdf_file(f'"{made}"') == made


class TestPageCount:
    def test_a_plain_page_tree_is_counted(self, tmp_path):
        assert pdf.page_count(write_pdf(tmp_path, pages=3)) == 3

    def test_a_page_tree_in_a_compressed_object_stream_is_counted(self, tmp_path):
        assert pdf.page_count(write_pdf(tmp_path, pages=7, compressed=True)) == 7

    def test_an_encrypted_pdf_is_not_guessed(self, tmp_path):
        assert pdf.page_count(write_pdf(tmp_path, encrypted=True)) is None

    def test_no_page_tree_is_not_guessed(self, tmp_path):
        bare = tmp_path / "bare.pdf"
        bare.write_bytes(b"%PDF-1.4\n%%EOF\n")
        assert pdf.page_count(str(bare)) is None


class TestSettings:
    def test_everything_asked_leaves_out_only_the_pictures(self):
        assert pdf.filter_value(["lines", "text", "hatches"]) == 8

    def test_lines_only_leaves_out_text_fills_and_pictures(self):
        assert pdf.filter_value(["lines"]) == 8 + 2 + 4

    def test_text_only_leaves_out_geometry_fills_and_pictures(self):
        assert pdf.filter_value(["text"]) == 8 + 1 + 4

    def test_an_unknown_kind_or_none_is_refused(self):
        with pytest.raises(ValueError, match="Unknown kind"):
            pdf.filter_value(["images"])
        with pytest.raises(ValueError, match="Say what"):
            pdf.filter_value([])

    @pytest.mark.parametrize(("before", "after"), [(6, 14), (7, 14), (0, 8), (15, 14), (8, 8)])
    def test_the_mode_keeps_his_choices_never_a_block_fills_as_hatches(self, before, after):
        assert pdf.mode_value(before) == after

    def test_numbers_no_drawing_has_are_refused(self):
        for page, scale, rotation in [(0, 1, 0), (1, 0, 0), (1, -2, 0), (1, 1, float("nan")), (1, 1e9, 0)]:
            with pytest.raises(ValueError):
                pdf.check_numbers(page, scale, rotation)


class TestWhatIsSent:
    def test_the_answers_come_in_the_order_the_command_asks(self):
        form = pdf.command_form(r"D:\Vendor PDFs\AHU-01.pdf", 3, [100.0, 200.0, 0.0], 50.0, 90.0)
        assert form == (
            '(command "_.-PDFIMPORT" "_File" "D:\\\\Vendor PDFs\\\\AHU-01.pdf" 3 '
            "(list 100.0 200.0 0.0) 50.0 90.0)"
        )

    def test_the_angle_is_brought_into_one_turn(self):
        assert pdf.command_form("a.pdf", 1, [0, 0], 1, -90).endswith(" 1.0 270.0)")

    def test_every_piece_is_one_whole_short_form(self):
        forms = pdf.import_forms(r"D:\A long folder name\with spaces\vendor drawing.pdf", 12, [1, 2, 3], 1, 0, "M-XREF-PDF")
        assert forms[pdf.COMMAND_PIECE - 1].startswith('(command "_.-PDFIMPORT"')
        for form in forms:
            assert split_forms(form) == [form]
            assert len(form) <= CHUNK_CHARS
            assert len(lisp_wrapper(form)) < FORM_MAX_CHARS

    def test_the_layer_is_made_only_after_the_command_and_only_when_asked(self):
        forms = pdf.import_forms("a.pdf", 1, [0, 0], 1, 0, "M-PDF")
        assert not any("vla-add" in f for f in forms[: pdf.COMMAND_PIECE])
        assert '"M-PDF"' in forms[pdf.WALK_PIECE - 1] and "tblsearch" in forms[pdf.WALK_PIECE - 1]
        assert "heron:l nil" in pdf.import_forms("a.pdf", 1, [0, 0], 1, 0, None)[pdf.WALK_PIECE - 1]

    def test_the_report_reads_back(self):
        report = pdf.parse_report("n=5;moved=4;failed=1", "-1.5,0,420,297", "LINE=3,MTEXT=1,HATCH=1,")
        assert report == {
            "count": 5, "moved": 4, "failed": 1,
            "box": {"min": [-1.5, 0.0], "max": [420.0, 297.0]},
            "by_type": {"LINE": 3, "HATCH": 1, "MTEXT": 1},
        }
        assert pdf.parse_report("n=0;moved=0;failed=0", "", "nil")["box"] is None
        with pytest.raises(ValueError):
            pdf.parse_report("nil", "", "")


# ---- the tool, against a stand-in AutoCAD -----------------------------------------------


class Layers:
    def __init__(self, names):
        self.names = list(names)

    @property
    def Count(self):  # noqa: N802 - COM name
        return len(self.names)

    def Item(self, i):  # noqa: N802 - COM name
        return type("Layer", (), {"Name": self.names[i]})()


class Doc:
    """Answers each piece the way AutoCAD would if PDFIMPORT asked exactly the six questions."""

    def __init__(self, acadver="26.0s (LMS Tech)", leave_open=False, imported="n=3;moved=3;failed=0",
                 box="0,0,420,297", types="LINE=2,MTEXT=1,", ucs_x=(1.0, 0.0, 0.0), ucs_y=(0.0, 1.0, 0.0),
                 no_pdf=False):
        self.variables = {
            "ACADVER": acadver, "PDFIMPORTMODE": 6, "PDFIMPORTFILTER": 5, "FILEDIA": 1, "AUNITS": 0,
            "ANGBASE": 0.5, "ANGDIR": 1, "OSMODE": 4133, LISP_RESULT_VAR: "his", LISP_CANCELLED_VAR: "",
            "CMDACTIVE": 0, "UCSORG": (0.0, 0.0, 0.0), "UCSXDIR": ucs_x, "UCSYDIR": ucs_y,
        }
        if no_pdf:
            del self.variables["PDFIMPORTMODE"]
        self.Layers = Layers(["0", "M-DUCT"])
        self.ActiveSpace = 1
        self.MSpace = False
        self.sent: list[str] = []
        self.during_command: dict = {}
        self.leave_open = leave_open
        self.answers = {"walk": imported, "box": box, "types": types}

    def GetVariable(self, name):  # noqa: N802 - COM name
        if name not in self.variables:
            raise KeyError(name)
        return self.variables[name]

    def SetVariable(self, name, value):  # noqa: N802 - COM name
        self.variables[name] = value

    def SendCommand(self, text):  # noqa: N802 - COM name
        self.sent.append(text)
        if "-PDFIMPORT" in text:
            self.during_command = dict(self.variables)
            self.variables[LISP_CANCELLED_VAR] = "PDFIMPORT" if self.leave_open else ""
            self.variables[LISP_RESULT_VAR] = "nil"
            if not self.leave_open:
                self.Layers.names.append("PDF_Geometry")
        elif "heron:pdfadd heron:e" in text:
            if '"M-PDF"' in text:
                self.Layers.names.append("M-PDF")
            self.variables[LISP_RESULT_VAR] = self.answers["walk"]
        elif "rtos (car heron:b)" in text:
            self.variables[LISP_RESULT_VAR] = self.answers["box"]
        elif "(itoa (cdr p))" in text:
            self.variables[LISP_RESULT_VAR] = self.answers["types"]
        else:
            self.variables[LISP_RESULT_VAR] = "nil"

    def StartUndoMark(self):  # noqa: N802 - COM name
        pass

    def EndUndoMark(self):  # noqa: N802 - COM name
        pass


@pytest.fixture
def acad(monkeypatch):
    holder: dict = {}

    def build(**kwargs) -> Doc:
        holder["doc"] = Doc(**kwargs)
        return holder["doc"]

    async def run(fn):
        return fn()

    def get_doc():
        return holder["doc"]

    monkeypatch.setattr(tool, "run", run)
    monkeypatch.setattr(tool, "get_doc", get_doc)
    monkeypatch.setattr(tool, "require_idle", lambda d: None)
    monkeypatch.setattr(advanced, "LISP_POLL_DELAY", 0.0)
    return build


def call(**kwargs) -> dict:
    answer = asyncio.run(tool.autocad_import_pdf(**kwargs))
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


def error(**kwargs) -> str:
    answer = asyncio.run(tool.autocad_import_pdf(**kwargs))
    assert answer.startswith("Error"), answer
    return answer


class TestTool:
    def test_it_is_a_change_tool(self):
        assert risk_of("autocad_import_pdf") is Risk.CHANGE

    def test_a_page_comes_in_and_is_reported(self, acad, tmp_path):
        doc = acad()
        made = write_pdf(tmp_path, "AHU 01.pdf", pages=3)
        answer = call(path=made, page=2, insertion=[1000, 2000], scale=50, layer="M-PDF")
        assert answer["imported"] == 3
        assert answer["by_type"] == {"LINE": 2, "MTEXT": 1}
        assert answer["box"] == {"min": [0.0, 0.0], "max": [420.0, 297.0]}
        assert answer["layer"] == "M-PDF" and answer["layer_created"] is True
        assert answer["moved_to_layer"] == 3
        assert answer["layers_added"] == ["PDF_Geometry"]
        assert answer["release"] == 2027 and answer["space"] == "model"
        assert "purge" in answer["note"]
        command = next(s for s in doc.sent if "-PDFIMPORT" in s)
        assert '"_File"' in command and "AHU 01.pdf" in command
        assert " 2 (list 1000.0 2000.0 0.0) 50.0 0.0)" in command

    def test_the_variables_are_set_for_the_command_and_all_put_back(self, acad, tmp_path):
        doc = acad()
        call(path=write_pdf(tmp_path), what=["lines"])
        during = doc.during_command
        assert during["FILEDIA"] == 0 and during["AUNITS"] == 0
        assert during["ANGBASE"] == 0.0 and during["ANGDIR"] == 0
        assert during["PDFIMPORTFILTER"] == 14 and during["PDFIMPORTMODE"] == 14
        assert during["OSMODE"] == 0
        for name, value in {"FILEDIA": 1, "ANGBASE": 0.5, "ANGDIR": 1, "PDFIMPORTFILTER": 5,
                            "PDFIMPORTMODE": 6, "OSMODE": 4133, LISP_RESULT_VAR: "his"}.items():
            assert doc.variables[name] == value, name

    def test_a_command_left_asking_is_cancelled_and_nothing_after_it_is_sent(self, acad, tmp_path):
        doc = acad(leave_open=True)
        answer = error(path=write_pdf(tmp_path, pages=4), layer="M-PDF")
        assert "cancelled" in answer and "nothing is left open" in answer and "it has 4" in answer
        assert len(doc.sent) == pdf.COMMAND_PIECE
        assert "M-PDF" not in doc.Layers.names
        assert doc.variables["FILEDIA"] == 1 and doc.variables["PDFIMPORTFILTER"] == 5

    def test_an_unknown_release_is_refused_and_nothing_is_set_or_sent(self, acad, tmp_path):
        doc = acad(acadver="23.1s (LMS Tech)")
        assert "nothing was sent" in error(path=write_pdf(tmp_path))
        assert doc.sent == [] and doc.variables["FILEDIA"] == 1

    def test_an_autocad_with_no_pdf_import_is_refused(self, acad, tmp_path):
        doc = acad(no_pdf=True)
        assert "no PDFIMPORTMODE" in error(path=write_pdf(tmp_path))
        assert doc.sent == []

    def test_a_missing_file_never_reaches_autocad(self, acad, tmp_path):
        doc = acad()
        assert "No file exists" in error(path=str(tmp_path / "gone.pdf"))
        assert doc.sent == []

    def test_a_page_past_the_last_is_refused(self, acad, tmp_path):
        doc = acad()
        assert "has 2 pages; there is no page 5" in error(path=write_pdf(tmp_path, pages=2), page=5)
        assert doc.sent == []

    def test_a_tilted_ucs_is_refused(self, acad, tmp_path):
        doc = acad(ucs_x=(1.0, 0.0, 0.0), ucs_y=(0.0, 0.0, 1.0))
        assert "tilted" in error(path=write_pdf(tmp_path))
        assert doc.sent == []

    def test_a_world_point_and_angle_are_typed_in_a_turned_ucs(self, acad, tmp_path):
        doc = acad(ucs_x=(0.0, 1.0, 0.0), ucs_y=(-1.0, 0.0, 0.0))
        answer = call(path=write_pdf(tmp_path), insertion=[0, 100], rotation=90)
        command = next(s for s in doc.sent if "-PDFIMPORT" in s)
        # World (0, 100) is UCS (100, 0) when the UCS is turned 90 degrees; world 90 is UCS 0.
        assert "(list 100.0 0.0 0.0) 1.0 0.0)" in command
        assert answer["insertion"] == [0.0, 100.0, 0.0]

    def test_a_page_with_nothing_to_bring_in_is_said_plainly(self, acad, tmp_path):
        acad(imported="n=0;moved=0;failed=0", box="", types="nil")
        answer = call(path=write_pdf(tmp_path))
        assert answer["imported"] == 0 and "scan" in answer["note"]

    def test_without_a_layer_the_pdf_layers_are_kept_and_named(self, acad, tmp_path):
        doc = acad()
        answer = call(path=write_pdf(tmp_path))
        assert answer["layer"] is None and answer["layer_created"] is False
        assert answer["layers_added"] == ["PDF_Geometry"]
        walk = next(s for s in doc.sent if "heron:pdfadd heron:e" in s)
        assert "heron:l nil" in walk
