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
#
# The set message also comes when the object simply has no such property, or
# turns the value down: pywin32 drops the HRESULT either way. So the server asks
# the object again itself (explain_set_failure, installed by core/connection.py)
# and a real refusal becomes PropertyRefused, which is never retried (#270).
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


# HRESULTs GetIDsOfNames gives for a name the object does not have (#270).
NO_MEMBER_HRESULTS = {
    -2147352570,  # 0x80020006 DISP_E_UNKNOWNNAME
    -2147352573,  # 0x80020003 DISP_E_MEMBERNOTFOUND
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


class PropertyRefused(AutocadError, AttributeError):
    """AutoCAD answered that this object has no such property, or will not take the value (#270, D-146).

    pywin32 gives both as "Property 'Item.CustomScale' can not be set.", the same
    words a busy AutoCAD gives, so they used to be asked again for ten seconds and
    end as "Outcome unknown: AutoCAD went busy" (#40). This one AutoCAD answered:
    it is a plain error at once, naming the property. It is still an
    AttributeError, so code that reads a refused set as "not there" reads it so.
    """

    def __init__(self, owner: str, prop: str, reason: str | None = None) -> None:
        self.owner = owner
        self.prop = prop
        self.reason = reason
        if reason is None:
            text = (
                f"AutoCAD has no property '{prop}' on this object ({owner}), so it could not "
                "be set. AutoCAD was not busy, so it was not asked again. This is a gap in "
                "Heron: report it with this message."
            )
        else:
            text = (
                f"AutoCAD would not set '{prop}' on this object ({owner}): {reason}. AutoCAD "
                "was not busy, so it was not asked again. Check the value, or set it by hand "
                "in AutoCAD."
            )
        super().__init__(text)


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
    if isinstance(exc, PropertyRefused):
        return False  # AutoCAD answered: no such property, or not this value (#270)
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


def explain_set_failure(obj: object, prop: str, value: object, failure: AttributeError) -> None:
    """Ask the object again why pywin32 could not set ``prop``, and say so (#270, D-146).

    Called only with pywin32's "Property '<x>' can not be set." AttributeError,
    which hides the HRESULT. The object is asked for the name's id, and when it
    has one, to take the value once more (a property set twice to one value is
    the same set):

    - no such name: PropertyRefused naming the property;
    - the value turned down for another reason: PropertyRefused with AutoCAD's words;
    - busy, a dead pointer, or anything unclear: ``failure`` goes up as it is, so
      the retry loop asks again, exactly as before;
    - taken this time: returns, the set is done.
    """
    if not _COM_SET_FAILURE.match(str(failure).strip()):
        raise failure
    state = getattr(obj, "__dict__", {})
    ole = state.get("_oleobj_")
    owner = str(state.get("_username_") or "?")
    if ole is None:
        raise failure
    try:
        found = ole.GetIDsOfNames(prop)
    except BaseException as exc:  # noqa: BLE001 - only a clear "no such name" changes the answer
        if hresult_of(exc) in NO_MEMBER_HRESULTS and not is_retryable(exc):
            raise PropertyRefused(owner, prop) from None
        raise failure from None
    dispid = found[0] if isinstance(found, (tuple, list)) else found
    try:
        ole.Invoke(dispid, 0, pythoncom.INVOKE_PROPERTYPUT, 0, value)
    except BaseException as exc:  # noqa: BLE001 - only AutoCAD's own refusal changes the answer
        if not isinstance(exc, pythoncom.com_error) or is_retryable(exc):
            raise failure from None
        raise PropertyRefused(owner, prop, com_message(exc)) from exc


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
