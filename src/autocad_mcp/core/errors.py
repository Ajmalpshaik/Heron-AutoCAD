"""Error types and COM error interpretation.

AutoCAD reports failure through pythoncom's ``com_error``, whose payload is a
nested tuple that is unreadable on its own. Everything here exists to turn that
into a sentence an agent can act on.
"""

from __future__ import annotations

import re

import pythoncom

# pywin32's dynamic dispatch reports an unresolvable COM member as a bare
# AttributeError, in one of two literal formats from win32com/client/dynamic.py:
#
#   __getattr__:  "AutoCAD.Application.Documents"   /  "<unknown>.SendCommand"
#   __setattr__:  "Property 'AddLine.Layer' can not be set."
#
# Both appear when AutoCAD is busy and GetIDsOfNames fails, which is exactly
# the transient condition the HRESULT would have marked retryable. A genuine
# Python AttributeError always reads "... has no attribute ...", which is what
# separates the two.
_COM_MEMBER_PATH = re.compile(r"^[\w<>. ]+\.[A-Za-z_]\w*$")
_COM_SET_FAILURE = re.compile(r"^Property '[^']+' can ?not be set\.?$")

# HRESULTs AutoCAD raises when it is merely busy and the call should be retried.
RETRYABLE_HRESULTS = {
    -2147418111,  # 0x80010001 RPC_E_CALL_REJECTED
    -2147417846,  # 0x8001010A RPC_E_SERVERCALL_RETRYLATER
    -2147417851,  # 0x80010105 RPC_E_SERVERFAULT
    -2146777998,  # 0x800AC472 VBA_E_IGNORE - AutoCAD is in a modal dialog
}

# The two that mean AutoCAD turned this one call away, unexecuted. The worker's
# message filter asks such a call again (message_filter.py); one that still
# arrives here was refused for the whole of that wait.
BUSY_REFUSAL_HRESULTS = {
    -2147418111,  # 0x80010001 RPC_E_CALL_REJECTED
    -2147417846,  # 0x8001010A RPC_E_SERVERCALL_RETRYLATER
}


# What is_busy goes by (D-100): the two refusals, and a modal dialog open. All
# three mean AutoCAD did not carry the call out. RPC_E_SERVERFAULT is left out:
# it says the call itself threw, which a "not there" fallback may rightly take.
BUSY_HRESULTS = BUSY_REFUSAL_HRESULTS | {
    -2146777998,  # 0x800AC472 VBA_E_IGNORE - AutoCAD is in a modal dialog
}


# HRESULTs meaning the pointer itself is dead: AutoCAD dropped the proxy (seen
# while a drawing opens). The cure is a fresh dispatch, same as StaleDispatchError.
DEAD_POINTER_HRESULTS = {
    -2147417848,  # 0x80010108 RPC_E_DISCONNECTED
}


class AutocadError(Exception):
    """An AutoCAD operation that could not be completed.

    Messages are written as instructions, not diagnoses: they say what the user
    or agent should do next.
    """


class OutcomeUnknown(AutocadError):
    """AutoCAD went busy after a write had started, so part of it may exist.

    Retrying would risk drawing the same thing twice, so the work is not
    re-run: the agent is told to look before it tries again. A write that is
    not a drawing (an UNDO sent as a command) gives its own words, which still
    start "Outcome unknown".
    """

    DEFAULT = (
        "Outcome unknown: AutoCAD went busy part-way through, so part of this "
        "may already be drawn (one Ctrl+Z reverses it). Read the drawing back "
        "before retrying."
    )

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.DEFAULT)


class StaleDispatchError(Exception):
    """The cached COM pointer stopped answering; retry with a fresh one.

    pywin32's dynamic dispatch resolves property names through
    ``GetIDsOfNames``. When AutoCAD is busy that call fails, and pywin32
    converts the COM error into a plain ``AttributeError`` — losing the
    HRESULT that would have marked it retryable. So a busy AutoCAD can surface
    as ``AttributeError: AutoCAD.Application.Documents`` rather than
    RPC_E_CALL_REJECTED.

    Both that case and a genuinely dead pointer are fixed the same way: drop
    the cached object, dispatch a new one, and try again. Raising this makes
    the retry loop do exactly that.
    """


def hresult_of(exc: BaseException) -> int | None:
    """The HRESULT of a COM error, or None for anything else."""
    if isinstance(exc, pythoncom.com_error) and exc.args:
        return exc.args[0]
    return None


def is_dispatch_failure(exc: BaseException) -> bool:
    """True when a COM member could not be resolved on a dispatch object.

    This covers the case pywin32 hides: ``GetIDsOfNames`` fails while AutoCAD
    is busy, pywin32 discards the HRESULT and raises a plain ``AttributeError``,
    and the call looks like a coding mistake rather than the transient
    condition it is. Both a busy AutoCAD and a genuinely dead pointer are fixed
    by re-dispatching and trying again.
    """
    if isinstance(exc, StaleDispatchError):
        return True
    if hresult_of(exc) in DEAD_POINTER_HRESULTS:
        return True
    if isinstance(exc, AttributeError):
        message = str(exc).strip()
        if "has no attribute" in message:
            return False
        return bool(
            _COM_MEMBER_PATH.match(message) or _COM_SET_FAILURE.match(message)
        )
    return False


def _says_busy(exc: BaseException) -> bool:
    """True when a COM error's description says AutoCAD was busy.

    The busy state also arrives wrapped in DISP_E_EXCEPTION, where only the
    description distinguishes it from a real failure.
    """
    if isinstance(exc, pythoncom.com_error) and len(exc.args) >= 3 and exc.args[2]:
        desc = str(exc.args[2][2] or "").lower()
        return any(
            phrase in desc
            for phrase in ("rejected by callee", "busy", "retry later")
        )
    return False


def is_retryable(exc: BaseException) -> bool:
    """True when the error means "AutoCAD is busy", not "this cannot work"."""
    if is_dispatch_failure(exc):
        return True
    if hresult_of(exc) in RETRYABLE_HRESULTS:
        return True
    return _says_busy(exc)


def is_busy(exc: BaseException) -> bool:
    """True only when AutoCAD turned this call away because it was busy (D-100).

    Narrower than is_retryable on purpose. A member pywin32 could not resolve
    is left out: asking an entity for a property its kind does not have (a
    line's Radius) gives the same AttributeError a busy AutoCAD can, and the
    tools rightly read that one as "not there".
    """
    return hresult_of(exc) in BUSY_HRESULTS or _says_busy(exc)


def raise_if_busy(exc: BaseException) -> None:
    """Let a busy refusal go up as it is; do nothing for any other error (D-100).

    Call it first in an ``except`` that would otherwise take a COM error for
    "not there", "use the default", or wrap it in a plain AutocadError. Up at
    connection._with_retry the refusal is asked again while nothing has been
    written yet, or becomes "Outcome unknown" once a write has begun: never a
    false failure, and never a quiet carry-on.
    """
    if is_busy(exc):
        raise exc


def com_message(exc: BaseException) -> str:
    """The most human-useful text available from a COM error.

    A busy refusal says so in words, so every message built from this one
    (there are dozens) tells the reader AutoCAD was busy, not broken.
    """
    if hresult_of(exc) in BUSY_REFUSAL_HRESULTS:
        said = str(exc.args[1]).strip() if len(exc.args) >= 2 and exc.args[1] else "call refused"
        return f"AutoCAD was busy and kept turning the call away ({said})"
    if isinstance(exc, pythoncom.com_error):
        if len(exc.args) >= 3 and exc.args[2]:
            source, desc = exc.args[2][1], exc.args[2][2]
            if desc:
                return str(desc).strip() + (f" (source: {source})" if source else "")
        if len(exc.args) >= 2 and exc.args[1]:
            return str(exc.args[1])
    return f"{type(exc).__name__}: {exc}"
