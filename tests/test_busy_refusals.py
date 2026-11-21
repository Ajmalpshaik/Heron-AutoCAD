"""A busy AutoCAD goes up as it is, never as a failure or a "not there" (D-100, #36).

D-57 let a refused call go up from ensure_layer and ensure_linetype. About 300
other ``except`` blocks still took a COM error for a failure, a missing name or
a default. Each now calls raise_if_busy first (core/errors.py); this file pins
the helper and the shared COM helpers it was added to, with fake COM objects.
tests/test_busy_sweep.py keeps new code from bringing the old way back.
"""

from __future__ import annotations

import pytest
import pythoncom

from autocad_mcp.core import connection
from autocad_mcp.core.errors import (
    AutocadError,
    OutcomeUnknown,
    is_busy,
    is_retryable,
    raise_if_busy,
)

REJECTED = pythoncom.com_error(-2147418111, "Call was rejected by callee.", None, None)
RETRY_LATER = pythoncom.com_error(-2147417846, "The message filter indicated that the application is busy.", None, None)
IN_A_DIALOG = pythoncom.com_error(-2146777998, "", None, None)
REJECTED_IN_WORDS = pythoncom.com_error(
    -2147352567, "Exception occurred.", (0, "AutoCAD", "Call was rejected by callee.", None, 0, 0), None
)
SERVER_FAULT = pythoncom.com_error(-2147417851, "The server threw an exception.", None, None)
KEY_NOT_FOUND = pythoncom.com_error(
    -2147352567, "Exception occurred.", (0, "AutoCAD", "Key not found", None, 0, -2145386476), None
)
# What pywin32 raises for a member the entity's kind does not have (a line's Radius).
NO_SUCH_MEMBER = AttributeError("IAcadLine.Radius")


class TestIsBusy:
    @pytest.mark.parametrize("exc", [REJECTED, RETRY_LATER, IN_A_DIALOG, REJECTED_IN_WORDS])
    def test_a_refused_call_is_busy(self, exc):
        assert is_busy(exc)
        assert is_retryable(exc), "every busy refusal is one the retry loop takes"

    @pytest.mark.parametrize(
        "exc", [KEY_NOT_FOUND, NO_SUCH_MEMBER, SERVER_FAULT, ValueError("bad number"), AutocadError("no")]
    )
    def test_anything_else_is_not(self, exc):
        assert not is_busy(exc)

    def test_a_member_the_entity_lacks_is_not_busy_though_the_retry_loop_takes_it(self):
        # The difference from is_retryable, on purpose: tools ask entities for
        # properties their kind may not have and read this as "not there".
        assert is_retryable(NO_SUCH_MEMBER) and not is_busy(NO_SUCH_MEMBER)


class TestRaiseIfBusy:
    def test_a_busy_refusal_goes_up_as_it_is(self):
        with pytest.raises(pythoncom.com_error) as err:
            try:
                raise REJECTED
            except BaseException as exc:  # noqa: BLE001
                raise_if_busy(exc)
                raise AssertionError("not reached") from exc
        assert err.value is REJECTED

    @pytest.mark.parametrize("exc", [KEY_NOT_FOUND, NO_SUCH_MEMBER, SERVER_FAULT])
    def test_any_other_error_is_left_to_the_except_block(self, exc):
        try:
            raise exc
        except BaseException as caught:  # noqa: BLE001
            raise_if_busy(caught)
            fallback = "used"
        assert fallback == "used"


class TestUpAtTheRetryLoop:
    """What the refusal becomes once raise_if_busy lets it up to connection._with_retry."""

    def test_before_a_write_it_is_asked_again(self, monkeypatch):
        monkeypatch.setattr(connection.time, "sleep", lambda seconds: None)
        tries = []

        def job():
            tries.append(1)
            try:
                if len(tries) < 3:
                    raise REJECTED
                return "layer list"
            except BaseException as exc:  # noqa: BLE001 - the shape of a tool's fallback
                raise_if_busy(exc)
                return "empty list"

        assert connection._with_retry(job) == "layer list"
        assert len(tries) == 3

    def test_after_a_write_began_it_is_outcome_unknown(self, monkeypatch):
        monkeypatch.setattr(connection.time, "sleep", lambda seconds: None)

        def job():
            connection.mark_writing()
            try:
                raise REJECTED
            except BaseException as exc:  # noqa: BLE001
                raise_if_busy(exc)
                raise AutocadError("Could not draw the line") from exc

        with pytest.raises(OutcomeUnknown):
            connection._with_retry(job)


# --- the shared helpers the tools go through: busy goes up, "not there" stays a fallback ----


def refusing(*_args, **_kwargs):
    raise REJECTED


def missing(*_args, **_kwargs):
    raise KEY_NOT_FOUND


class Obj:
    """A fake COM object: attributes given are answers, callables are called as methods."""

    def __init__(self, **members) -> None:
        self.__dict__.update(members)


class Refuses:
    """A fake COM object that turns away every property read and method call."""

    def __getattr__(self, name):
        raise REJECTED


class TestEntityReads:
    def test_curve_length_does_not_take_a_refusal_for_a_missing_property(self):
        from autocad_mcp.acad.curves import curve_length

        with pytest.raises(pythoncom.com_error):
            curve_length(type("Line", (), {"ObjectName": "AcDbLine", "Length": property(refusing)})())

    def test_curve_length_still_tries_the_next_property(self):
        from autocad_mcp.acad.curves import curve_length

        class Arc:
            ObjectName = "AcDbArc"
            ArcLength = 3.5

            def __getattr__(self, name):
                raise AttributeError(f"IAcadArc.{name}")

        assert curve_length(Arc()) == 3.5

    def test_one_property_read_lets_a_refusal_up(self):
        from autocad_mcp.acad.entities import _try

        with pytest.raises(pythoncom.com_error):
            _try(refusing, "default")
        assert _try(lambda: (_ for _ in ()).throw(NO_SUCH_MEMBER), "default") == "default"

    def test_attributes_and_extents_let_a_refusal_up(self):
        from autocad_mcp.acad.entities import bounding_box, read_attributes

        with pytest.raises(pythoncom.com_error):
            read_attributes(Obj(GetAttributes=refusing))
        with pytest.raises(pythoncom.com_error):
            bounding_box(Obj(GetBoundingBox=refusing))
        assert read_attributes(Obj(GetAttributes=missing)) == {}
        assert bounding_box(Obj(GetBoundingBox=missing)) is None

    def test_a_refused_handle_is_not_called_unknown(self):
        from autocad_mcp.acad.entities import resolve_handle

        with pytest.raises(pythoncom.com_error):
            resolve_handle(Obj(HandleToObject=refusing), "2A")
        with pytest.raises(AutocadError, match="No entity with handle '2A'"):
            resolve_handle(Obj(HandleToObject=missing), "2A")


class TestDrawingTables:
    def test_a_refused_selection_set_look_up_adds_no_second_set(self):
        from autocad_mcp.acad.selection import make_selection_set

        added = []
        sets = Obj(Item=refusing, Add=lambda name: added.append(name))
        with pytest.raises(pythoncom.com_error):
            make_selection_set(Obj(SelectionSets=sets))
        assert added == []

    def test_a_new_selection_set_is_still_added(self):
        from autocad_mcp.acad.selection import make_selection_set

        added = []
        sets = Obj(Item=missing, Add=lambda name: added.append(name) or "set")
        assert make_selection_set(Obj(SelectionSets=sets)) == "set"
        assert len(added) == 1

    def test_a_refused_linetype_load_is_not_called_not_found(self):
        from autocad_mcp.acad import tables

        doc = Obj(Linetypes=Obj(Item=missing, Load=refusing))
        with pytest.raises(pythoncom.com_error):
            tables.ensure_linetype(doc, "HIDDEN")

    def test_a_linetype_in_neither_file_is_still_not_found(self):
        from autocad_mcp.acad import tables

        doc = Obj(Linetypes=Obj(Item=missing, Load=missing))
        with pytest.raises(AutocadError, match="not found in acadiso.lin or acad.lin"):
            tables.ensure_linetype(doc, "NOSUCH")

    def test_a_refused_layer_read_is_not_a_default_state(self):
        from autocad_mcp.acad.tables import describe_layer

        with pytest.raises(pythoncom.com_error):
            describe_layer(Refuses())

    def test_a_refused_table_alignment_goes_up(self):
        from autocad_mcp.acad.table_cells import middle_rows

        with pytest.raises(pythoncom.com_error):
            middle_rows(Obj(GetAlignment=lambda row: 1, SetAlignment=refusing))
        assert middle_rows(Obj(GetAlignment=lambda row: 1, SetAlignment=missing)) == 0


class TestWhereThePointsGo:
    def test_a_refused_ucs_read_is_not_the_world_ucs(self):
        from autocad_mcp.tools._shared import current_ucs

        with pytest.raises(pythoncom.com_error):
            current_ucs(Obj(GetVariable=refusing))

    def test_an_unreadable_ucs_is_still_the_world_one(self):
        from autocad_mcp.acad.coords import Ucs
        from autocad_mcp.tools._shared import current_ucs

        assert current_ucs(Obj(GetVariable=missing)) == Ucs()


class TestConnection:
    def test_a_refused_command_check_is_not_idle(self):
        with pytest.raises(pythoncom.com_error):
            connection.require_idle(Obj(GetVariable=refusing))
        connection.require_idle(Obj(GetVariable=missing))  # best effort: no answer, no refusal

    def test_a_refused_window_read_is_not_another_autocad(self):
        with pytest.raises(pythoncom.com_error):
            connection._pid_of(Refuses())

    def test_a_busy_autocad_is_not_reported_as_none_running(self, monkeypatch):
        monkeypatch.setattr(connection.win32com.client, "GetActiveObject", refusing)
        with pytest.raises(pythoncom.com_error):
            connection._AppCache()._dispatch(launch_if_needed=False)

    def test_no_autocad_at_all_is_still_said(self, monkeypatch):
        monkeypatch.setattr(connection.win32com.client, "GetActiveObject", missing)
        with pytest.raises(AutocadError, match="No running AutoCAD instance was found"):
            connection._AppCache()._dispatch(launch_if_needed=False)


# --- the gate: a busy AutoCAD is never "UNDO is off" or "Discard took" ------------------


@pytest.fixture
def gate_on_busy_autocad(monkeypatch):
    """The gate's own COM reads, through the real retry loop, on an AutoCAD that refuses."""
    from autocad_mcp.core import gate

    clock = [0.0]
    monkeypatch.setattr(connection.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(connection.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    async def run(fn):
        return connection._with_retry(fn)

    doc = Obj(GetVariable=refusing, HandleToObject=refusing)
    monkeypatch.setattr(gate, "run", run)
    monkeypatch.setattr(gate, "get_app", lambda: Obj(ActiveDocument=doc))
    return gate


def test_a_busy_undo_check_is_not_undo_off(gate_on_busy_autocad):
    import asyncio

    with pytest.raises(AutocadError, match="stayed busy"):
        asyncio.run(gate_on_busy_autocad._mark())


def test_a_busy_look_after_discard_is_not_gone(gate_on_busy_autocad):
    import asyncio

    with pytest.raises(AutocadError, match="stayed busy"):
        asyncio.run(gate_on_busy_autocad._still_there(["2A"]))


def test_a_job_whose_undo_mark_stayed_busy_is_refused_in_words(monkeypatch):
    """The gate answers "AutoCAD stayed busy", never a bare tool error, and never runs the job."""
    import asyncio

    from test_gate import FakeBridge

    from autocad_mcp.core import gate
    from autocad_mcp.core.registry import tool_errors

    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "on")
    FakeBridge.refuse, FakeBridge.ask_to_keep, FakeBridge.calls = None, True, []

    async def probe():
        return 1234, r"C:\a.dwg"

    async def busy_mark():
        raise AutocadError("AutoCAD stayed busy for 10s and never accepted the request. Press Esc.")

    monkeypatch.setattr(gate, "Bridge", FakeBridge)
    monkeypatch.setattr(gate, "_probe", probe)
    monkeypatch.setattr(gate, "_mark", busy_mark)
    gate.reset(looked_at=r"C:\a.dwg")
    ran = []

    async def autocad_draw_line() -> str:
        ran.append(1)
        return '{"created": true, "handle": "2A"}'

    result = asyncio.run(tool_errors(autocad_draw_line)())
    assert result.startswith("REFUSED - AutoCAD stayed busy"), result
    assert "Error: AutoCAD stayed busy" in result
    assert ran == []
    assert [c for c in FakeBridge.calls if c[0] == "end"], "the plug-in's job is still ended"


# --- the small readers the tools share: a refusal goes up, a missing property gives the default --

GETTER_READERS = [
    ("autocad_mcp.acad.entities", "_try"),
    ("autocad_mcp.tools.drafting", "_try"),
    ("autocad_mcp.tools.solids", "_try"),
    ("autocad_mcp.tools.edit2d", "_try"),
    ("autocad_mcp.tools.xrefs", "_try"),
    ("autocad_mcp.tools.settings", "_safe"),
    ("autocad_mcp.tools.layer_states", "_try"),
    ("autocad_mcp.tools.sheets", "_try"),
    ("autocad_mcp.tools.materials", "_try"),
    ("autocad_mcp.tools.dimensions_edit", "_try"),
    ("autocad_mcp.tools.drawing_report", "_try"),
]
NAMED_READERS = [
    ("autocad_mcp.tools.sheets", "_read"),
    ("autocad_mcp.tools.views", "_read"),
    ("autocad_mcp.tools.convert", "_read"),
]


def _reader(module: str, name: str):
    import importlib

    return getattr(importlib.import_module(module), name)


@pytest.mark.parametrize(("module", "name"), GETTER_READERS)
def test_a_reader_lets_a_refusal_up(module, name):
    read = _reader(module, name)
    with pytest.raises(pythoncom.com_error):
        read(refusing, "default")
    assert read(lambda: (_ for _ in ()).throw(NO_SUCH_MEMBER), "default") == "default"
    assert read(missing, "default") == "default"


@pytest.mark.parametrize(("module", "name"), NAMED_READERS)
def test_a_property_reader_lets_a_refusal_up(module, name):
    read = _reader(module, name)
    with pytest.raises(pythoncom.com_error):
        read(Refuses(), "Width", 1.0)
    assert read(Obj(), "Width", 1.0) == 1.0


@pytest.mark.parametrize(
    ("module", "name"),
    [("autocad_mcp.tools.drafting", "_try"), ("autocad_mcp.tools.solids", "_try"),
     ("autocad_mcp.tools.sheets", "_try"), ("autocad_mcp.tools.dimensions_edit", "_try")],
)
def test_a_restore_a_cancel_or_a_redraw_never_raises(module, name):
    # busy_ok: putting OSMODE back in a finally, pressing Esc on the way to the real
    # error, a redraw after the work: a refusal there must not hide the answer.
    assert _reader(module, name)(refusing, "default", busy_ok=True) == "default"


def test_between_drawings_reader_lets_a_refusal_up():
    from autocad_mcp.tools.between_drawings import _read

    with pytest.raises(pythoncom.com_error):
        _read(Refuses(), "Name")
