"""A get of a member the object lacks answers at once; a busy AutoCAD is still asked again (#280, D-153).

pywin32 answers every late-bound member it cannot resolve with "AutoCAD.AcDbLine.Radius",
busy or not, so a tool that read a line's Radius by mistake was asked again for ten
seconds and ended as "Lost the COM connection". The server now asks the object itself,
only after the get failed (core/connection.check_member_gets -> errors.explain_get_failure).

The fake class below raises exactly what pywin32's dynamic.CDispatch.__getattr__ raises
when GetIDsOfNames fails: "<owner>.<name>", with no HRESULT.
"""

from __future__ import annotations

import pytest
import pythoncom
import win32com.client

from autocad_mcp.core import connection, errors
from autocad_mcp.core.errors import (
    AutocadError,
    MemberMissing,
    OutcomeUnknown,
    is_busy,
    is_dispatch_failure,
    is_retryable,
)

UNKNOWN_NAME = -2147352570  # DISP_E_UNKNOWNNAME
CALL_REJECTED = -2147418111  # RPC_E_CALL_REJECTED


def com_error(hresult: int, text: str = "") -> pythoncom.com_error:
    return pythoncom.com_error(hresult, text, None, None)


class FakeOle:
    """The PyIDispatch under the object: answers GetIDsOfNames as told, and counts the asks."""

    def __init__(self, ids=None) -> None:
        self.ids = ids if ids is not None else {}
        self.asked: list[str] = []

    def GetIDsOfNames(self, name):  # noqa: N802 - COM's name
        self.asked.append(name)
        found = self.ids.get(name)
        if isinstance(found, BaseException):
            raise found
        if found is None:
            raise com_error(UNKNOWN_NAME, "Unknown name.")
        return found


def make_class():
    """A class that fails a get the way pywin32's late-bound object does, wrapped as the server wraps it."""

    class LateBound:
        def __init__(self, ole, username="IAcadLine", values=None) -> None:
            self.__dict__["_oleobj_"] = ole
            self.__dict__["_username_"] = username
            self.__dict__["values"] = dict(values or {})
            self.__dict__["gets"] = 0

        def __getattr__(self, name):
            self.__dict__["gets"] += 1
            if name.startswith("_") and name.endswith("_"):
                raise AttributeError(name)
            values = self.__dict__["values"]
            if name in values:
                return values[name]
            ole = self.__dict__["_oleobj_"]
            try:
                ole.GetIDsOfNames(name)
            except pythoncom.com_error:
                raise AttributeError(f"{self._username_}.{name}") from None
            raise AttributeError(f"{self._username_}.{name}")  # resolved but not served by the fake

    connection.check_member_gets(LateBound)
    return LateBound


@pytest.fixture(autouse=True)
def _fresh_memory():
    errors._KNOWN_MISSING.clear()
    yield
    errors._KNOWN_MISSING.clear()


def test_a_member_the_object_does_not_have_answers_at_once_with_its_name():
    line = make_class()(FakeOle())
    with pytest.raises(MemberMissing) as caught:
        _ = line.Radius
    error = caught.value
    assert "'Radius'" in str(error) and "IAcadLine" in str(error)
    assert "not busy" in str(error)
    assert error.member == "Radius" and error.owner == "IAcadLine"
    # Never read as busy, never retried; still an AttributeError for "not there" readers.
    assert not is_dispatch_failure(error)
    assert not is_retryable(error)
    assert not is_busy(error)
    assert isinstance(error, AttributeError) and isinstance(error, AutocadError)


def test_hasattr_and_getattr_defaults_are_unchanged():
    line = make_class()(FakeOle(), values={"Layer": "0"})
    assert hasattr(line, "Layer") and not hasattr(line, "Radius")
    assert getattr(line, "Radius", None) is None
    assert getattr(line, "Closed", False) is False
    assert getattr(line, "Layer", None) == "0"
    # A dunder name is pywin32's own "not there": never looked into, never asked of AutoCAD.
    ole = FakeOle()
    assert getattr(make_class()(ole), "__deepcopy__", None) is None
    assert ole.asked == []


def test_a_get_that_works_asks_autocad_nothing_more():
    ole = FakeOle()
    line = make_class()(ole, values={"Length": 1000.0})
    assert line.Length == 1000.0
    assert ole.asked == []  # no diagnosis before or after a get that works


def test_a_busy_autocad_still_gives_the_old_error_and_is_retried():
    rejected = com_error(CALL_REJECTED, "Call was rejected by callee.")
    line = make_class()(FakeOle(ids={"Layer": rejected}))
    with pytest.raises(AttributeError) as caught:
        _ = line.Layer
    assert not isinstance(caught.value, MemberMissing)
    assert str(caught.value) == "IAcadLine.Layer"
    assert is_dispatch_failure(caught.value) and is_retryable(caught.value)
    # hasattr while busy is False, as before.
    assert not hasattr(line, "Layer")


def test_a_name_found_on_the_second_ask_keeps_the_old_error():
    # The first ask failed (busy), the second found the id: busy a moment ago, asked again as before.
    ole = FakeOle(ids={"Layer": 5})

    class Flaky:
        def __init__(self) -> None:
            self.__dict__["_oleobj_"] = ole
            self.__dict__["_username_"] = "IAcadLine"

        def __getattr__(self, name):
            raise AttributeError(f"IAcadLine.{name}")

    connection.check_member_gets(Flaky)
    with pytest.raises(AttributeError) as caught:
        _ = Flaky().Layer
    assert not isinstance(caught.value, MemberMissing)
    assert is_retryable(caught.value)


def test_a_second_miss_on_the_same_kind_of_object_asks_autocad_nothing():
    ole = FakeOle()
    cls = make_class()
    for _ in range(3):
        assert getattr(cls(ole), "Closed", False) is False
    assert ole.asked == ["Closed"] * 4  # pywin32's own ask each time (3); Heron's only once
    # Another kind of object is asked afresh.
    with pytest.raises(MemberMissing):
        _ = cls(ole, username="IAcadCircle").Closed


def test_an_object_of_unknown_kind_is_never_remembered():
    ole = FakeOle()
    cls = make_class()
    for _ in range(2):
        with pytest.raises(MemberMissing):
            _ = cls(ole, username="<unknown>").Radius
    assert ole.asked == ["Radius"] * 4  # pywin32's ask and Heron's, both times
    assert errors._KNOWN_MISSING == set()


def test_an_object_without_its_com_pointer_keeps_the_old_error():
    class Bare:
        def __getattr__(self, name):
            raise AttributeError(f"Item.{name}")

    connection.check_member_gets(Bare)
    with pytest.raises(AttributeError) as caught:
        _ = Bare().Layer
    assert not isinstance(caught.value, MemberMissing)
    assert is_dispatch_failure(caught.value)


def test_other_attribute_errors_are_left_alone():
    ole = FakeOle()

    class Plain:
        def __init__(self) -> None:
            self.__dict__["_oleobj_"] = ole

        def __getattr__(self, name):
            raise AttributeError(f"'Plain' object has no attribute '{name}'")

    connection.check_member_gets(Plain)
    with pytest.raises(AttributeError) as caught:
        _ = Plain().x
    assert not isinstance(caught.value, MemberMissing)
    assert ole.asked == []


def test_the_check_is_installed_once_on_pywins_late_bound_class():
    installed = win32com.client.CDispatch.__getattr__
    assert getattr(installed, "heron_checked", False)
    connection.check_member_gets(win32com.client.CDispatch)
    assert win32com.client.CDispatch.__getattr__ is installed


def test_a_class_without_getattr_is_left_alone():
    class Fixed:
        pass

    connection.check_member_gets(Fixed)
    assert not hasattr(Fixed, "__getattr__")


def test_a_missing_member_escaping_a_tool_answers_at_once_not_lost_connection(monkeypatch):
    """The issue's case: a tool reads line.Radius; it used to be retried 10 s, then 'Lost the COM connection'."""
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)
    invalidated = []
    monkeypatch.setattr(connection, "invalidate", lambda: invalidated.append(1))
    line = make_class()(FakeOle())
    calls = []

    def work():
        calls.append(1)
        return line.Radius

    with pytest.raises(MemberMissing):
        connection._with_retry(work)
    assert calls == [1] and invalidated == []  # answered at once, the connection kept


def test_after_a_write_began_a_missing_member_is_a_plain_error_not_outcome_unknown(monkeypatch):
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)
    line = make_class()(FakeOle())

    def work():
        connection.mark_writing()
        return line.Radius

    with pytest.raises(MemberMissing):
        connection._with_retry(work)


def test_after_a_write_began_a_busy_get_is_still_outcome_unknown(monkeypatch):
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)
    line = make_class()(FakeOle(ids={"Layer": com_error(CALL_REJECTED, "Call was rejected by callee.")}))

    def work():
        connection.mark_writing()
        return line.Layer

    with pytest.raises(OutcomeUnknown):
        connection._with_retry(work)


def test_before_a_write_a_busy_get_is_asked_again_until_it_answers(monkeypatch):
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)
    monkeypatch.setattr(connection, "invalidate", lambda: None)
    rejected = com_error(CALL_REJECTED, "Call was rejected by callee.")
    ole = FakeOle(ids={"Layer": rejected})
    line = make_class()(ole)
    calls = []

    def work():
        calls.append(1)
        if len(calls) == 2:
            line.__dict__["values"]["Layer"] = "WALLS"  # AutoCAD free again
        return line.Layer

    assert connection._with_retry(work) == "WALLS"
    assert len(calls) == 2
