"""A property AutoCAD will not set answers at once; a busy AutoCAD is still asked again (#270, D-146).

pywin32 answers every late-bound property it cannot set with "Property
'Item.CustomScale' can not be set.", busy or not, so a layout's CustomScale
(a property a layout does not have) was asked again for ten seconds and ended
as "Outcome unknown: AutoCAD went busy" (#40). The server now asks the object
itself why (core/connection.check_property_sets -> errors.explain_set_failure).

The fake class below raises exactly what pywin32's dynamic.CDispatch.__setattr__
raises when the name is not in the type information: the message, with no HRESULT.
"""

from __future__ import annotations

import pytest
import pythoncom
import win32com.client

from autocad_mcp.core import connection
from autocad_mcp.core.errors import (
    AutocadError,
    OutcomeUnknown,
    PropertyRefused,
    is_busy,
    is_dispatch_failure,
    is_retryable,
)

UNKNOWN_NAME = -2147352570  # DISP_E_UNKNOWNNAME
CALL_REJECTED = -2147418111  # RPC_E_CALL_REJECTED
INVALID_ARG = -2147024809  # E_INVALIDARG
DISP_EXCEPTION = -2147352567  # DISP_E_EXCEPTION


def com_error(hresult: int, text: str = "", description: str | None = None) -> pythoncom.com_error:
    info = (0, "AutoCAD", description, None, 0, hresult) if description else None
    return pythoncom.com_error(hresult, text, info, None)


class FakeOle:
    """The PyIDispatch under the object: answers GetIDsOfNames and Invoke as told."""

    def __init__(self, ids=None, invoke=None) -> None:
        self.ids = ids if ids is not None else {}
        self.invoke = list(invoke or [])  # what each Invoke does: None = taken, or an error
        self.invoked: list[tuple] = []

    def GetIDsOfNames(self, name):  # noqa: N802 - COM's name
        found = self.ids.get(name)
        if isinstance(found, BaseException):
            raise found
        if found is None:
            raise com_error(UNKNOWN_NAME, "Unknown name.")
        return found

    def Invoke(self, dispid, lcid, flags, result, value):  # noqa: N802 - COM's name
        self.invoked.append((dispid, flags, value))
        step = self.invoke.pop(0) if self.invoke else None
        if isinstance(step, BaseException):
            raise step
        return None


def make_class():
    """A class that fails a set the way pywin32's late-bound object does, wrapped as the server wraps it."""

    class LateBound:
        def __init__(self, ole, username="Item") -> None:
            self.__dict__["_oleobj_"] = ole
            self.__dict__["_username_"] = username

        def __setattr__(self, name, value):
            if name in self.__dict__:
                self.__dict__[name] = value
                return
            raise AttributeError(f"Property '{self._username_}.{name}' can not be set.")

    connection.check_property_sets(LateBound)
    return LateBound


def test_a_property_the_object_does_not_have_answers_at_once_with_its_name():
    layout = make_class()(FakeOle())
    with pytest.raises(PropertyRefused) as caught:
        layout.CustomScale = 1.0
    error = caught.value
    assert "'CustomScale'" in str(error)
    assert "not busy" in str(error)
    assert error.prop == "CustomScale" and error.reason is None
    # Never read as busy, never retried; still an AttributeError for "not there" readers.
    assert not is_dispatch_failure(error)
    assert not is_retryable(error)
    assert not is_busy(error)
    assert isinstance(error, AttributeError) and isinstance(error, AutocadError)


def test_a_value_the_object_turns_down_answers_with_autocads_words():
    ole = FakeOle(ids={"CenterPlot": 7}, invoke=[com_error(DISP_EXCEPTION, "Exception occurred.", "Invalid input")])
    layout = make_class()(ole)
    with pytest.raises(PropertyRefused) as caught:
        layout.CenterPlot = True
    assert "'CenterPlot'" in str(caught.value)
    assert "Invalid input" in str(caught.value)
    assert not is_retryable(caught.value)
    assert ole.invoked == [(7, pythoncom.INVOKE_PROPERTYPUT, True)]


def test_a_busy_autocad_still_gives_the_old_error_and_is_retried():
    # GetIDsOfNames itself turned away: busy, exactly as before.
    busy = make_class()(FakeOle(ids={"Layer": com_error(CALL_REJECTED, "Call was rejected by callee.")}))
    with pytest.raises(AttributeError) as caught:
        busy.Layer = "0"
    assert not isinstance(caught.value, PropertyRefused)
    assert is_dispatch_failure(caught.value) and is_retryable(caught.value)

    # The name is there, and the second ask is turned away too: busy.
    ole = FakeOle(ids={"Layer": 3}, invoke=[com_error(CALL_REJECTED, "Call was rejected by callee.")])
    with pytest.raises(AttributeError) as caught:
        make_class()(ole).Layer = "0"
    assert not isinstance(caught.value, PropertyRefused)
    assert is_retryable(caught.value)


def test_a_second_ask_that_is_taken_is_a_done_set():
    ole = FakeOle(ids={"Layer": 3}, invoke=[None])
    make_class()(ole).Layer = "WALLS"  # no error
    assert ole.invoked == [(3, pythoncom.INVOKE_PROPERTYPUT, "WALLS")]


def test_an_object_without_its_com_pointer_keeps_the_old_error():
    class Bare:
        def __setattr__(self, name, value):
            raise AttributeError(f"Property 'Item.{name}' can not be set.")

    connection.check_property_sets(Bare)
    with pytest.raises(AttributeError) as caught:
        Bare().Layer = "0"
    assert not isinstance(caught.value, PropertyRefused)
    assert is_dispatch_failure(caught.value)


def test_other_attribute_errors_are_left_alone():
    class Plain:
        def __setattr__(self, name, value):
            raise AttributeError(f"'Plain' object has no attribute '{name}'")

    connection.check_property_sets(Plain)
    with pytest.raises(AttributeError) as caught:
        Plain().x = 1
    assert not isinstance(caught.value, PropertyRefused)


def test_the_check_is_installed_once_on_pywins_late_bound_class():
    installed = win32com.client.CDispatch.__setattr__
    assert getattr(installed, "heron_checked", False)
    connection.check_property_sets(win32com.client.CDispatch)
    assert win32com.client.CDispatch.__setattr__ is installed


def test_after_a_write_began_a_missing_property_is_a_plain_error_not_outcome_unknown(monkeypatch):
    """Row D8's case (#40): the sheet is added, then a property it does not have is set."""
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)
    layout = make_class()(FakeOle())
    calls = []

    def work():
        calls.append(1)
        connection.mark_writing()
        layout.CustomScale = 1.0

    with pytest.raises(PropertyRefused):
        connection._with_retry(work)
    assert calls == [1]  # answered at once, not asked again


def test_after_a_write_began_a_busy_set_is_still_outcome_unknown(monkeypatch):
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)
    layout = make_class()(FakeOle(ids={"Layer": com_error(CALL_REJECTED, "Call was rejected by callee.")}))

    def work():
        connection.mark_writing()
        layout.Layer = "0"

    with pytest.raises(OutcomeUnknown):
        connection._with_retry(work)


def test_before_a_write_a_busy_set_is_asked_again_until_it_is_taken(monkeypatch):
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)
    rejected = com_error(CALL_REJECTED, "Call was rejected by callee.")
    ole = FakeOle(ids={"Layer": rejected})
    layout = make_class()(ole)
    calls = []

    def work():
        calls.append(1)
        if len(calls) == 2:
            ole.ids["Layer"] = 3  # AutoCAD free again
        layout.Layer = "0"
        return "set"

    assert connection._with_retry(work) == "set"
    assert len(calls) == 2
