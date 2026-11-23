"""Text typed into AutoCAD's command line refuses control characters (#242, D-133).

``lisp_string`` escapes control characters (#207, D-129), but a few tools type text with
``SendCommand`` and no LISP string around it. A raw newline there is Enter and a raw Esc
cancels the command, so a caller's string could end the command and have the rest read as new
input. Review of every typed path:

* views.py ``-VIEW _Save {name}``: the view name came from the caller and ``validate_name`` lets
  control characters through. FIXED here: ``refuse_control`` (acad/lisp.py).
* drafting.py and dimensions_edit.py ``typed``: only numbers and hex handles are typed. Proven safe.
* coordinates.py ``line + newline``: only two fixed lines are ever passed. Proven safe.
* sheets.py ``mview_command``: only numbers. Proven safe.
* solids.py ``_.VSCURRENT {option}``: the option comes from a fixed table by a checked key. Proven safe.

Offline, with stand-ins for the COM document: nothing here ran in AutoCAD (NEEDS-CHECKING Group BA).
"""

from __future__ import annotations

import asyncio
import re

import pytest
from pydantic import TypeAdapter, ValidationError

from autocad_mcp.acad.lisp import refuse_control
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import (
    coordinates,
    dimensions_edit,
    drafting,
    sheets,
    solids,
    views,
)

# What a typed line may hold: printable ASCII, never a control character.
PRINTABLE = re.compile(r"[\x20-\x7e]*")

CONTROLS = [
    "A\nB", "A\rB", "A\tB", "A\x1bB", "A\x1b\x1bB", "A\x00B", "A\x7fB", "A\x03B",
    "A\u0085B", "A B", "A B",
    "VIEW1\n", "\x1bVIEW1",
]


class Untouched:
    """A document that must never be reached: any use is a failed test."""

    def __getattr__(self, name):
        raise AssertionError(f"AutoCAD was touched ({name}) before the refusal")


class TestRefuseControl:
    @pytest.mark.parametrize("text", CONTROLS)
    def test_a_control_character_is_refused_in_plain_words(self, text):
        with pytest.raises(AutocadError) as caught:
            refuse_control(text, "view name")
        message = str(caught.value)
        assert message.startswith("The view name holds ")
        assert "cannot be typed into AutoCAD's command line" in message
        assert message.endswith("Nothing was typed.")

    @pytest.mark.parametrize(
        ("text", "named"),
        [("A\nB", "a line break"), ("A\rB", "a carriage return"), ("A\tB", "a tab"), ("A\x1bB", "an Esc character"),
         ("A\x00B", "a NUL character"), ("A\x03B", "U+0003"), ("A\u0085B", "U+0085")],
    )
    def test_the_character_is_named(self, text, named):
        with pytest.raises(AutocadError, match=re.escape(named)):
            refuse_control(text)

    @pytest.mark.parametrize("text", ["LIVING-3D", "view_1", "Plan 5\" pipe", "café", "عرض-3D", "കാഴ്ച", "中文", "x" * 200])
    def test_ordinary_text_and_other_scripts_pass_unchanged(self, text):
        assert refuse_control(text, "name") == text

    def test_it_is_the_same_definition_of_control_as_the_lisp_side(self):
        # One helper, not a copy: it uses the characters escape_control already knows (D-129).
        from autocad_mcp.acad.lisp import UnsendableText, escape_control

        for char in ("\x00", "\x1b", "\x7f", "\u0085", " "):
            with pytest.raises(AutocadError):
                refuse_control(f"a{char}b")
        # What escape_control would turn into an escape or refuse is exactly what is refused here.
        for char in ("\n", "\t", "\x1b"):
            assert escape_control(char) != char
        with pytest.raises(UnsendableText):
            escape_control("\x00")


class TestViewName:
    """views.py: the one path that typed a caller's string."""

    @pytest.mark.parametrize("name", CONTROLS)
    def test_save_view_from_screen_refuses_before_anything_is_touched(self, name, monkeypatch):
        monkeypatch.setattr(views, "get_doc", lambda: Untouched())
        result = asyncio.run(views.autocad_save_view(name=name, from_screen=True))
        assert result.startswith("Error: The view name holds ")
        assert "Nothing was typed." in result

    def test_the_corners_and_handles_path_refuses_it_too(self, monkeypatch):
        # Not typed there (Views.Add takes the name over COM), but a control character is never a valid view name.
        monkeypatch.setattr(views, "get_doc", lambda: Untouched())
        result = asyncio.run(views.autocad_save_view(name="A\x1bB", corner1=[0, 0], corner2=[10, 10]))
        assert result.startswith("Error: The view name holds an Esc character")

    def test_a_trailing_newline_is_not_hidden_by_the_clean_up(self, monkeypatch):
        # validate_name strips the name, which would drop a trailing newline unseen.
        monkeypatch.setattr(views, "get_doc", lambda: Untouched())
        result = asyncio.run(views.autocad_save_view(name="LIVING\n", from_screen=True))
        assert "line break" in result

    def test_the_typing_site_refuses_before_the_old_view_is_deleted(self):
        # _save_screen guards itself: the old view of that name is never deleted for a bad name.
        with pytest.raises(AutocadError, match="Esc character"):
            views._save_screen(Untouched(), "A\x1bB", True)

    def test_a_good_name_is_typed_as_it_is(self, monkeypatch):
        sent: list[str] = []

        class Doc:
            def StartUndoMark(self):  # noqa: N802 - COM name
                pass

            def EndUndoMark(self):  # noqa: N802 - COM name
                pass

            def SendCommand(self, text):  # noqa: N802 - COM name
                sent.append(text)

        monkeypatch.setattr(views, "_views", lambda d: {})
        monkeypatch.setattr(views, "_command_done", lambda d: True)
        with pytest.raises(AutocadError, match="no view called"):
            views._save_screen(Doc(), "LIVING-3D", False)  # the read-back finds nothing: only what was typed matters
        assert sent == ["_.-VIEW _Save LIVING-3D\n"]


class TestAlreadySafe:
    """Paths whose typed text is built from numbers, hex handles or fixed words only."""

    def test_wipeout_types_only_numbers(self):
        # Corners go through float(): text that is not a number is a ValueError, and a number with a
        # line break around it (which float() accepts) comes out as the number alone.
        typed = drafting.wipeout_command([["1\n", " 2 "], [5, 2], [5.5, 9.25], [1e-12, 1e20]])
        lines = typed.split("\n")
        assert lines[0] == "_.WIPEOUT"
        assert lines[-2:] == ["", ""]  # the closing blank line
        for line in lines[1:-2]:
            assert re.fullmatch(r"_non \*-?\d+(\.\d+)?,-?\d+(\.\d+)?", line), line
        for text in lines:
            assert PRINTABLE.fullmatch(text)

    @pytest.mark.parametrize("bad", ["1\x1b", "1;(startapp)", "a\nb", "(startapp \"x\")"])
    def test_wipeout_refuses_text_that_is_not_a_number(self, bad):
        with pytest.raises(ValueError):
            drafting.wipeout_command([[bad, 0], [5, 2], [5, 9]])

    @pytest.mark.parametrize("remove", [False, True])
    def test_dimbreak_types_only_hex_handles_and_its_own_words(self, remove):
        typed = dimensions_edit.dimbreak_command(["1A", " 2b ", "FF00FF"], remove)
        lines = typed.split("\n")
        assert lines[:2] == ["_.DIMBREAK", "_M"]
        assert lines[2:5] == ['(handent "1A")', '(handent "2b")', '(handent "FF00FF")']
        assert lines[5:] == ["", "_R" if remove else "_B", ""]
        for text in lines:
            assert PRINTABLE.fullmatch(text)

    @pytest.mark.parametrize("bad", ["1A\n_Y", "1A\x1b", "1A\x1b\x1b(startapp)", "1A;", '1A")(startapp "x', "1A 2B", "", "G1", "0" * 17])
    def test_dimbreak_refuses_anything_that_is_not_a_handle(self, bad):
        with pytest.raises(ValueError, match="is not a handle"):
            dimensions_edit.dimbreak_command([bad])
        with pytest.raises(AutocadError, match="is not a handle"):
            dimensions_edit._check_handles([bad])

    def test_a_handle_with_only_outer_whitespace_is_typed_without_it(self):
        assert dimensions_edit.dimbreak_command(["1A\n"]).split("\n")[2] == '(handent "1A")'

    def test_the_ucs_command_takes_its_mode_from_a_closed_list(self):
        adapter = TypeAdapter(coordinates.SetMode)
        for good in ("world", "view"):
            assert adapter.validate_python(good) == good
        for bad in ("world\n", "view\x1b", "world _Y", "World", "x\n_.ERASE"):
            with pytest.raises(ValidationError):
                adapter.validate_python(bad)

    @pytest.mark.parametrize("mode", ["world", "view", "named", "origin", "world\n", "view\x1b_.ERASE\n", "bogus"])
    def test_the_ucs_tool_types_only_its_two_fixed_lines(self, mode, monkeypatch):
        typed: list[list[str]] = []

        class Ucs:
            def describe(self, name):
                return {}

        class Doc:
            def StartUndoMark(self):  # noqa: N802 - COM name
                pass

            def EndUndoMark(self):  # noqa: N802 - COM name
                pass

        async def now(fn):
            return fn()

        monkeypatch.setattr(coordinates, "run", now)
        monkeypatch.setattr(coordinates, "get_doc", lambda: Doc())
        monkeypatch.setattr(coordinates, "require_idle", lambda d: None)
        monkeypatch.setattr(coordinates, "_send", lambda doc, lines: typed.append(list(lines)))
        monkeypatch.setattr(coordinates, "_named_ucs", lambda doc: {"A": object()})
        monkeypatch.setattr(coordinates, "_store", lambda doc, ucs, name: object())
        monkeypatch.setattr(coordinates, "current_ucs", lambda doc: Ucs())
        monkeypatch.setattr(coordinates, "_ucs_name", lambda doc: "")
        monkeypatch.setattr(coordinates, "advice", lambda ucs: None)
        asyncio.run(coordinates.autocad_set_ucs(mode=mode, name="A"))
        assert typed in ([], [["_.UCS _World"]], [["_.UCS _View"]])
        assert all(PRINTABLE.fullmatch(line) for lines in typed for line in lines)

    @pytest.mark.parametrize("centre", [(0, 0), (1234.5678, -9876.54321), (1e-9, 1e9)])
    def test_mview_types_only_numbers(self, centre):
        typed = sheets.mview_command(centre[0], centre[1], 840.0, 594.0)
        assert re.fullmatch(r"_\.MVIEW -?\d+\.\d{4},-?\d+\.\d{4} -?\d+\.\d{4},-?\d+\.\d{4} ", typed), typed
        assert PRINTABLE.fullmatch(typed)

    def test_vscurrent_options_come_from_a_fixed_table(self):
        assert set(solids.VISUAL_STYLE_OPTIONS) == set(solids.VISUAL_STYLES)
        for option in solids.VISUAL_STYLE_OPTIONS.values():
            assert re.fullmatch(r"_[A-Za-z0-9]+", option), option

    @pytest.mark.parametrize("style", ["realistic\x1b", "x-ray\n_.ERASE", "Hidden; (startapp)", "\n"])
    def test_a_visual_style_that_is_not_on_the_list_is_refused_before_autocad_is_touched(self, style, monkeypatch):
        monkeypatch.setattr(solids, "get_doc", lambda: Untouched())
        result = asyncio.run(solids.autocad_set_3d_view(visual_style=style))
        assert result.startswith("Error: ") and "is not a visual style" in result
