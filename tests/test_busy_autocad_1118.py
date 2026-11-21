"""A moment of busy AutoCAD must not stop a run (Luxury Suite 3 rehearsal, 2026-11-18).

The no-pause video player stopped twice although AutoCAD had done nothing wrong:

- autocad_run_lisp reported "timed out" within half a second while AutoCAD
  redrew after a layer-off or a camera-view restore. One refused read of USERS1
  ended the wait, so a finished expression looked like a failed one.
- autocad_create_layer stopped with "Could not create layer 'A-ANNO-TTLE': Call
  was rejected by callee." while drawing tabs were switched. AutoCAD turned one
  call away; ensure_layer took the refusal for "no such layer", and the second
  refusal was reported as a plain failure. Heron's retry in connection.run never
  saw it, and could not have re-run the tool anyway: a write had begun.

The cure for the second is a COM message filter on the worker thread
(core/message_filter.py): a call AutoCAD turned away was never carried out, so
asking for that one call again cannot draw anything twice.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import sys
import threading

import pytest
import pythoncom

from autocad_mcp.acad import tables
from autocad_mcp.core import connection, message_filter
from autocad_mcp.core.errors import AutocadError, com_message, is_retryable
from autocad_mcp.tools import advanced
from autocad_mcp.tools.advanced import LISP_CANCELLED_VAR, LISP_RESULT_VAR

BUSY = pythoncom.com_error(-2147418111, "Call was rejected by callee.", None, None)
RETRY_LATER = pythoncom.com_error(-2147417846, "The message filter indicated that the application is busy.", None, None)
KEY_NOT_FOUND = pythoncom.com_error(-2147352567, "Exception occurred.", (0, "AutoCAD", "Key not found", None, 0, -2145386476), None)

needs_com_thread = pytest.mark.skipif(sys.platform != "win32", reason="registers the COM message filter on a real Windows thread")


class FakeTime:
    """A clock that only moves when something waits on it."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


# --- run_lisp: a busy read is not the end of the wait ---------------------------------


class LispDoc:
    """Answers run_lisp the way a busy AutoCAD would: the expression runs, reads fail for a while."""

    def __init__(self, busy_reads: int = 0, busy_sets: dict[str, int] | None = None, clock: FakeTime | None = None,
                 seconds_per_refusal: float = 0.0) -> None:
        self.variables = {LISP_RESULT_VAR: "mine", LISP_CANCELLED_VAR: "also mine", "OSMODE": 675, "CMDACTIVE": 0}
        self.sent: list[str] = []
        self.busy_reads = busy_reads
        self.busy_sets = dict(busy_sets or {})
        self.reads_after_send = 0
        self.clock = clock
        self.seconds_per_refusal = seconds_per_refusal

    def _refuse(self) -> None:
        if self.clock is not None:
            self.clock.now += self.seconds_per_refusal
        raise BUSY

    def GetVariable(self, name):
        if self.sent and name == LISP_RESULT_VAR:
            self.reads_after_send += 1
            if self.busy_reads:
                self.busy_reads -= 1
                self._refuse()
        return self.variables[name]

    def SetVariable(self, name, value):
        if self.sent and self.busy_sets.get(name):
            self.busy_sets[name] -= 1
            self._refuse()
        self.variables[name] = value

    def SendCommand(self, text):
        self.sent.append(text)
        self.variables[LISP_CANCELLED_VAR] = ""
        self.variables[LISP_RESULT_VAR] = "42"

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


@pytest.fixture
def lisp(monkeypatch):
    def build(**kwargs) -> LispDoc:
        doc = LispDoc(**kwargs)

        async def run(fn):
            return fn()

        monkeypatch.setattr(advanced, "run", run)
        monkeypatch.setattr(advanced, "get_doc", lambda: doc)
        monkeypatch.setattr(advanced, "require_idle", lambda d: None)
        return doc

    return build


def run_lisp(expression: str = "(+ 40 2)") -> dict:
    return json.loads(asyncio.run(advanced.autocad_run_lisp(expression=expression)))


class TestRunLispWhileAutocadRedraws:
    def test_a_few_refused_reads_still_bring_the_result_back(self, lisp, monkeypatch):
        monkeypatch.setattr(advanced, "time", FakeTime())
        lisp(busy_reads=3)
        answer = run_lisp()
        assert answer["timed_out"] is False
        assert answer["result"] == "42"

    def test_reads_refused_for_ever_stop_at_the_full_wait(self, lisp, monkeypatch):
        monkeypatch.setattr(advanced, "time", FakeTime())
        monkeypatch.setattr(advanced, "LISP_POLL_ATTEMPTS", 5)
        doc = lisp(busy_reads=10**6)
        answer = run_lisp()
        assert answer["timed_out"] is True
        assert doc.reads_after_send == 5
        assert "busy" in answer["note"]

    def test_slow_refusals_do_not_stretch_the_wait_past_its_bound(self, lisp, monkeypatch):
        # With the message filter each refused read can take a few seconds.
        clock = FakeTime()
        monkeypatch.setattr(advanced, "time", clock)
        doc = lisp(busy_reads=10**6, clock=clock, seconds_per_refusal=3.0)
        run_lisp()
        bound = advanced.LISP_POLL_ATTEMPTS * advanced.LISP_POLL_DELAY
        assert 3 <= doc.reads_after_send <= 5
        assert clock.now <= bound + 3.0 + advanced.LISP_POLL_DELAY

    def test_result_variable_is_put_back_after_one_refusal(self, lisp, monkeypatch):
        monkeypatch.setattr(advanced, "time", FakeTime())
        doc = lisp(busy_sets={LISP_RESULT_VAR: 1, LISP_CANCELLED_VAR: 1})
        run_lisp()
        assert doc.variables[LISP_RESULT_VAR] == "mine"
        assert doc.variables[LISP_CANCELLED_VAR] == "also mine"

    def test_object_snaps_are_put_back_after_one_refusal(self, lisp, monkeypatch):
        monkeypatch.setattr(advanced, "time", FakeTime())
        doc = lisp(busy_sets={"OSMODE": 1})
        run_lisp()
        assert doc.variables["OSMODE"] == 675


# --- create_layer: a refused call is AutoCAD busy, never "no such layer" ------------------


class Layers:
    def __init__(self, item_error=None, add_error=None) -> None:
        self.item_error, self.add_error = item_error, add_error
        self.added: list[str] = []

    def Item(self, name):
        raise self.item_error

    def Add(self, name):
        if self.add_error is not None:
            raise self.add_error
        self.added.append(name)
        return object()


class TableDoc:
    def __init__(self, layers: Layers) -> None:
        self.Layers = layers


class TestEnsureLayerWhenAutocadIsBusy:
    def test_a_refused_look_up_is_not_taken_for_a_missing_layer(self):
        layers = Layers(item_error=BUSY)
        with pytest.raises(pythoncom.com_error) as err:
            tables.ensure_layer(TableDoc(layers), "A-ANNO-TTLE")
        assert is_retryable(err.value)
        assert layers.added == []

    def test_a_refused_add_stays_a_busy_signal(self):
        layers = Layers(item_error=KEY_NOT_FOUND, add_error=BUSY)
        with pytest.raises(pythoncom.com_error) as err:
            tables.ensure_layer(TableDoc(layers), "A-ANNO-TTLE")
        assert is_retryable(err.value)

    def test_a_missing_layer_is_still_created(self):
        layers = Layers(item_error=KEY_NOT_FOUND)
        _, created = tables.ensure_layer(TableDoc(layers), "A-ANNO-TTLE")
        assert created and layers.added == ["A-ANNO-TTLE"]


class Linetypes:
    def __init__(self, item_error) -> None:
        self.item_error = item_error
        self.loaded: list[str] = []

    def Item(self, name):
        raise self.item_error

    def Load(self, name, source):
        self.loaded.append(name)


def test_a_refused_linetype_look_up_is_not_taken_for_a_missing_linetype():
    linetypes = Linetypes(BUSY)
    doc = type("Doc", (), {"Linetypes": linetypes})()
    with pytest.raises(pythoncom.com_error):
        tables.ensure_linetype(doc, "HIDDEN")
    assert linetypes.loaded == []


class TestBusyWording:
    def test_a_refused_call_says_autocad_was_busy(self):
        assert "AutoCAD was busy" in com_message(BUSY)
        assert "AutoCAD was busy" in com_message(RETRY_LATER)

    def test_other_errors_keep_their_own_words(self):
        assert "busy" not in com_message(KEY_NOT_FOUND)
        assert com_message(KEY_NOT_FOUND) == "Key not found (source: AutoCAD)"


# --- connection: the retry before a write is bounded in time, not only in tries ---------


def test_slow_refusals_do_not_stretch_the_retry_past_its_window(monkeypatch):
    clock = FakeTime()
    monkeypatch.setattr(connection, "time", clock)
    attempts: list[int] = []

    def work():
        attempts.append(1)
        clock.now += 3.0  # each refusal waited in the message filter first
        raise BUSY

    with pytest.raises(AutocadError) as err:
        connection._with_retry(work)
    assert "busy" in str(err.value)
    assert 3 <= len(attempts) <= 5
    assert clock.now <= connection.RETRY_WINDOW + 3.0 + connection.RETRY_DELAY


# --- the message filter ------------------------------------------------------------------


class TestRetryDecision:
    def test_a_rejected_call_is_asked_again_after_a_short_wait(self):
        assert message_filter.retry_delay(0, message_filter.SERVERCALL_REJECTED) >= 100

    def test_retry_later_is_asked_again_too(self):
        assert message_filter.retry_delay(0, message_filter.SERVERCALL_RETRYLATER) >= 100

    def test_the_wait_grows_after_the_first_second(self):
        early = message_filter.retry_delay(0, message_filter.SERVERCALL_REJECTED)
        later = message_filter.retry_delay(1500, message_filter.SERVERCALL_REJECTED)
        assert later > early

    def test_it_gives_up_at_its_budget(self):
        budget = message_filter.BUDGET_MS
        assert message_filter.retry_delay(budget, message_filter.SERVERCALL_REJECTED) == message_filter.CANCEL
        assert message_filter.retry_delay(budget - 1, message_filter.SERVERCALL_REJECTED) != message_filter.CANCEL

    def test_anything_else_is_handed_straight_back(self):
        assert message_filter.retry_delay(0, 0) == message_filter.CANCEL
        assert message_filter.retry_delay(0, 7) == message_filter.CANCEL

    def test_the_budget_is_short(self):
        # Each refused call may wait this long; the tool-level window adds to it.
        assert message_filter.BUDGET_MS <= 5000


def _on_sta_thread(job):
    """Run job() on a fresh single-threaded-apartment thread, like the COM worker."""
    box: dict = {}

    def body():
        pythoncom.CoInitialize()
        try:
            box["value"] = job()
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            box["error"] = exc
        finally:
            pythoncom.CoUninitialize()

    thread = threading.Thread(target=body)
    thread.start()
    thread.join(10)
    if "error" in box:
        raise box["error"]
    return box["value"]


def _registered_filter() -> int | None:
    """The filter COM holds for this thread (registered again straight after reading it)."""
    register = ctypes.WinDLL("ole32").CoRegisterMessageFilter
    register.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    register.restype = ctypes.c_long
    previous = ctypes.c_void_p()
    assert register(None, ctypes.byref(previous)) == 0
    if previous.value:
        register(previous.value, ctypes.byref(ctypes.c_void_p()))
    return previous.value


@needs_com_thread
class TestFilterPlumbing:
    def test_windows_accepts_the_filter_on_an_apartment_thread(self):
        def job():
            installed = message_filter.install()
            return installed, _registered_filter()

        installed, held = _on_sta_thread(job)
        assert installed is True
        assert held == message_filter.filter_address()

    def test_com_reaches_the_decision_through_the_vtable(self):
        def job():
            message_filter.install()
            address = _registered_filter()
            vtable = message_filter.vtable_at(address)
            return (
                vtable.RetryRejectedCall(address, None, 50, message_filter.SERVERCALL_REJECTED),
                vtable.RetryRejectedCall(address, None, message_filter.BUDGET_MS, message_filter.SERVERCALL_REJECTED),
                vtable.HandleInComingCall(address, 0, None, 0, None),
                vtable.MessagePending(address, None, 0, 0),
            )

        retry, give_up, incoming, pending = _on_sta_thread(job)
        assert retry == message_filter.retry_delay(50, message_filter.SERVERCALL_REJECTED)
        assert give_up == message_filter.CANCEL
        assert incoming == message_filter.SERVERCALL_ISHANDLED
        assert pending == message_filter.PENDINGMSG_WAITDEFPROCESS

    def test_query_interface_answers_only_for_itself(self):
        def job():
            message_filter.install()
            address = _registered_filter()
            vtable = message_filter.vtable_at(address)
            out = ctypes.c_void_p()
            mine = vtable.QueryInterface(address, ctypes.byref(message_filter.IID_IMESSAGEFILTER), ctypes.byref(out))
            got = out.value
            other = message_filter.GUID(0x12345678, 0, 0, (ctypes.c_ubyte * 8)(*range(8)))
            out2 = ctypes.c_void_p(1)
            refused = vtable.QueryInterface(address, ctypes.byref(other), ctypes.byref(out2))
            return mine, got, refused, out2.value

        mine, got, refused, cleared = _on_sta_thread(job)
        assert mine == 0 and got == message_filter.filter_address()
        assert refused == message_filter.E_NOINTERFACE and not cleared

    def test_the_wait_is_budgeted_per_job_not_per_call(self):
        # A tool that swallows refusals call after call must not wait 3 s for each of them.
        def job():
            message_filter.install()
            address = _registered_filter()
            vtable = message_filter.vtable_at(address)
            ask = lambda: vtable.RetryRejectedCall(address, None, 0, message_filter.SERVERCALL_REJECTED)  # noqa: E731
            waits = []
            for _ in range(100):
                delay = ask()
                if delay == message_filter.CANCEL:
                    break
                waits.append(delay)
            after_budget = ask()
            message_filter.new_job()
            next_job = ask()
            return waits, after_budget, next_job

        waits, after_budget, next_job = _on_sta_thread(job)
        assert sum(waits) <= message_filter.BUDGET_MS
        assert sum(waits) > message_filter.BUDGET_MS - message_filter.LATER_DELAY_MS
        assert after_budget == message_filter.CANCEL
        assert next_job == message_filter.FIRST_DELAY_MS

    def test_a_thread_without_com_is_refused_quietly(self):
        box: dict = {}
        thread = threading.Thread(target=lambda: box.setdefault("installed", message_filter.install()))
        thread.start()
        thread.join(10)
        assert box["installed"] is False


def test_the_com_worker_installs_the_filter_on_its_own_thread(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(message_filter, "install", lambda: seen.append(threading.current_thread().name) or True)
    worker = connection._ComWorker()
    assert worker.submit(lambda: "done") == "done"
    assert seen == ["autocad-com"]


def test_every_job_on_the_worker_starts_with_a_fresh_budget(monkeypatch):
    started: list[str] = []
    monkeypatch.setattr(message_filter, "install", lambda: True)
    monkeypatch.setattr(message_filter, "new_job", lambda: started.append(threading.current_thread().name))
    worker = connection._ComWorker()
    worker.submit(lambda: 1)
    worker.submit(lambda: 2)
    assert started == ["autocad-com", "autocad-com"]
