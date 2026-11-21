"""A COM message filter for the worker thread: a call AutoCAD turned away is asked again.

When AutoCAD is busy for a moment (a drawing tab switching, a redraw starting)
it turns an incoming COM call away: RPC_E_CALL_REJECTED, or
RPC_E_SERVERCALL_RETRYLATER. With no filter registered, COM hands that straight
back to Python, and one refused property read becomes a failed tool (Luxury
Suite 3 rehearsal, 2026-11-18: "Could not create layer 'A-ANNO-TTLE': Call was
rejected by callee.").

A refused call was never carried out, so asking for that one call again cannot
draw anything twice. That is the difference from connection._with_retry, which
re-runs a whole tool and so must stop once a write has begun. The filter asks
again with a short wait between tries, then lets the refusal through to the
caller as before. The waiting is budgeted per job, not per call (BUDGET_MS in
all for one piece of work on the worker): many places in the tools swallow a
refused call and go on to the next, and 3 s for each of them would hold the
only COM thread for minutes. Once a job has spent its budget, every refusal
fails fast, as it did before this file existed.

pywin32 has no CoRegisterMessageFilter, so the filter is a small, stateless COM
object made with ctypes: one vtable, one instance, both kept for the life of
the process. It is registered on the COM worker thread only (connection.py),
after CoInitialize. If Windows refuses it, nothing changes: Heron works as it
did before this file existed.
"""

from __future__ import annotations

import ctypes
import threading

# What the server's own filter said about the call (dwRejectType).
SERVERCALL_ISHANDLED = 0
SERVERCALL_REJECTED = 1
SERVERCALL_RETRYLATER = 2
# MessagePending: let Windows deal with the message the usual way.
PENDINGMSG_WAITDEFPROCESS = 2
# RetryRejectedCall: -1 as a DWORD. COM returns the refusal to the caller.
CANCEL = 0xFFFFFFFF

# The most one job (one piece of work on the COM worker) waits on refusals, in
# all. Short on purpose: connection._with_retry adds its own window on top
# before a write.
BUDGET_MS = 3000
# Wait between tries: COM retries at once below 100 ms, which would only spin.
FIRST_DELAY_MS = 100
LATER_DELAY_MS = 250
FIRST_PHASE_MS = 1000

S_OK = 0
E_NOINTERFACE = -2147467262  # 0x80004002
E_POINTER = -2147467261  # 0x80004003


def retry_delay(elapsed_ms: int, reject_type: int, spent_ms: int = 0) -> int:
    """What RetryRejectedCall answers: milliseconds to wait, or CANCEL.

    Only a refusal (REJECTED) or a "later" (RETRYLATER) is asked again: while
    the call itself is younger than BUDGET_MS, and while the job has waited
    less than BUDGET_MS in all (spent_ms) including this wait.
    """
    if reject_type not in (SERVERCALL_REJECTED, SERVERCALL_RETRYLATER):
        return CANCEL
    if elapsed_ms >= BUDGET_MS:
        return CANCEL
    delay = FIRST_DELAY_MS if elapsed_ms < FIRST_PHASE_MS else LATER_DELAY_MS
    if spent_ms + delay > BUDGET_MS:
        return CANCEL
    return delay


# What the current job has waited so far, per thread (the filter is per thread).
_job = threading.local()


def new_job() -> None:
    """Give the calling thread's next job a full budget (the worker calls it per job)."""
    _job.spent_ms = 0


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _ole_guid(data1: int) -> GUID:
    """{xxxxxxxx-0000-0000-C000-000000000046}, the form of COM's own interfaces."""
    return GUID(data1, 0, 0, (ctypes.c_ubyte * 8)(0xC0, 0, 0, 0, 0, 0, 0, 0x46))


IID_IUNKNOWN = _ole_guid(0x00000000)
IID_IMESSAGEFILTER = _ole_guid(0x00000016)
_OWN_IIDS = (bytes(IID_IUNKNOWN), bytes(IID_IMESSAGEFILTER))

_QueryInterface = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)
)
_AddRef = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
_Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
_HandleInComingCall = ctypes.WINFUNCTYPE(
    ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p
)
_RetryRejectedCall = ctypes.WINFUNCTYPE(
    ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong
)
_MessagePending = ctypes.WINFUNCTYPE(
    ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong
)


class _Vtable(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", _QueryInterface),
        ("AddRef", _AddRef),
        ("Release", _Release),
        ("HandleInComingCall", _HandleInComingCall),
        ("RetryRejectedCall", _RetryRejectedCall),
        ("MessagePending", _MessagePending),
    ]


class _Filter(ctypes.Structure):
    _fields_ = [("vtable", ctypes.POINTER(_Vtable))]


# Every callback catches everything: an exception escaping a ctypes callback
# returns 0, and 0 from RetryRejectedCall means "try again at once" - a spin.


def _query_interface(this, riid, ppv):
    try:
        if not ppv:
            return E_POINTER
        if riid and bytes(riid.contents) in _OWN_IIDS:
            ppv[0] = this
            return S_OK
        ppv[0] = None
        return E_NOINTERFACE
    except BaseException:  # noqa: BLE001
        return E_NOINTERFACE


def _add_ref(this):
    return 1  # one static object, never freed


def _release(this):
    return 1


def _handle_incoming_call(this, call_type, caller, tick_count, interface_info):
    return SERVERCALL_ISHANDLED


def _retry_rejected_call(this, callee, tick_count, reject_type):
    try:
        spent = getattr(_job, "spent_ms", 0)
        delay = retry_delay(int(tick_count), int(reject_type), spent)
        if delay != CANCEL:
            _job.spent_ms = spent + delay
        return delay
    except BaseException:  # noqa: BLE001
        return CANCEL


def _message_pending(this, callee, tick_count, pending_type):
    return PENDINGMSG_WAITDEFPROCESS


# Kept at module level for the life of the process: COM holds raw pointers to
# these, and a collected callback would crash this server, not raise.
_CALLBACKS = (
    _QueryInterface(_query_interface),
    _AddRef(_add_ref),
    _Release(_release),
    _HandleInComingCall(_handle_incoming_call),
    _RetryRejectedCall(_retry_rejected_call),
    _MessagePending(_message_pending),
)
_VTABLE = _Vtable(*_CALLBACKS)
_FILTER = _Filter(ctypes.pointer(_VTABLE))


def filter_address() -> int:
    """Where the filter object lives: the pointer COM is given."""
    return ctypes.addressof(_FILTER)


def vtable_at(address: int) -> _Vtable:
    """The vtable of a filter object at address (for the tests)."""
    return _Filter.from_address(address).vtable.contents


def install() -> bool:
    """Register the filter for the calling thread. False when Windows refuses; never raises.

    Call it on a single-threaded-apartment thread, after CoInitialize: a thread
    without COM, or in the multithreaded apartment, is refused by Windows.
    """
    try:
        register = ctypes.WinDLL("ole32").CoRegisterMessageFilter
        register.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        register.restype = ctypes.c_long
        previous = ctypes.c_void_p()
        return register(filter_address(), ctypes.byref(previous)) == S_OK
    except BaseException:  # noqa: BLE001 - no filter means Heron as before
        return False
