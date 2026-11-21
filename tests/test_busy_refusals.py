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
