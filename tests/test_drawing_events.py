"""The wrong-drawing guard reads the plug-in's document events (#48, D-98). No AutoCAD.

Comparing the drawing in front with the one autocad_status checked misses
what happened in between. The plug-in now records AutoCAD's document events
as they happen, and the gate asks for those since its check: a drawing
closed and opened again, or a restarted AutoCAD, needs a new check; a Save As
of the checked drawing is followed. An older plug-in that cannot tell leaves
the guard exactly as it was.
"""

from __future__ import annotations

import asyncio

import pytest

from autocad_mcp.core import bridge as bridge_module
from autocad_mcp.core import connection, gate
from autocad_mcp.core.bridge import NOTHING_SENT, Bridge, BridgeRefused
from autocad_mcp.core.drawing_events import Mark, Verdict, judge, same, short
from autocad_mcp.core.registry import tool_errors

A = r"C:\jobs\a.dwg"
B = r"C:\jobs\b.dwg"
MARK = Mark(pid=1234, epoch="e1", seq=4)


def history(*events, epoch="e1", lost=False, active=None):
    numbered = [{"seq": 5 + i, "at": f"10:0{i}:00", "was": "", **event} for i, event in enumerate(events)]
    return {"epoch": epoch, "seq": 4 + len(events), "active": active, "lost": lost, "events": numbered}


# --- the judging, pure --------------------------------------------------------


class TestJudge:
    def test_nothing_known_leaves_the_name_compare_to_decide(self):
        assert judge(A, A, None, 1234, history()) == Verdict()
        assert judge(A, A, MARK, 1234, None) == Verdict()

    def test_nothing_happened(self):
        assert judge(A, A, MARK, 1234, history()) == Verdict(seen=4)

    def test_a_switch_away_and_back_is_the_same_drawing(self):
        events = history({"kind": "activated", "drawing": B}, {"kind": "activated", "drawing": A})
        assert judge(A, A, MARK, 1234, events) == Verdict(seen=6)

    def test_closed_and_opened_again_needs_a_new_check(self):
        events = history({"kind": "closed", "drawing": A}, {"kind": "opened", "drawing": A})
        verdict = judge(A, A, MARK, 1234, events)
        assert verdict.refusal is not None
        assert "a.dwg was closed at 10:00:00 and opened again since Heron checked it" in verdict.refusal
        assert "autocad_status" in verdict.refusal and verdict.refusal.endswith(NOTHING_SENT)

    def test_closed_with_another_in_front_says_both(self):
        verdict = judge(A, B, MARK, 1234, history({"kind": "closed", "drawing": A}))
        assert "a.dwg was closed at 10:00:00 since Heron checked it, and b.dwg is in front now" in verdict.refusal

    def test_closing_another_drawing_is_not_news(self):
        assert judge(A, A, MARK, 1234, history({"kind": "closed", "drawing": B})) == Verdict(seen=5)

    def test_another_autocad_session_needs_a_new_check(self):
        assert "started again" in judge(A, A, MARK, 1234, history(epoch="e2")).refusal
        assert "another AutoCAD is in front" in judge(A, A, MARK, 999, history()).refusal

    def test_a_save_as_is_followed(self):
        renamed = r"C:\jobs\a-rev2.dwg"
        events = history({"kind": "saved", "drawing": renamed, "was": A})
        assert judge(A, renamed, MARK, 1234, events) == Verdict(follow=renamed, seen=5)

    def test_an_unsaved_drawing_saved_as_a_file_is_followed(self):
        events = history({"kind": "saved", "drawing": A, "was": "Drawing1.dwg"})
        assert judge("Drawing1.dwg", A, MARK, 1234, events) == Verdict(follow=A, seen=5)

    def test_a_save_as_then_the_old_file_opened_again_needs_a_new_check(self):
        renamed = r"C:\jobs\a-rev2.dwg"
        events = history({"kind": "saved", "drawing": renamed, "was": A}, {"kind": "opened", "drawing": A},
                         {"kind": "activated", "drawing": A})  # fmt: skip
        verdict = judge(A, A, MARK, 1234, events)
        assert "a.dwg was opened at 10:01:00, after Heron checked a drawing" in verdict.refusal
        assert verdict.refusal.endswith(NOTHING_SENT)

    def test_a_second_copy_of_the_checked_file_opened_needs_a_new_check(self):
        assert judge(A, A, MARK, 1234, history({"kind": "opened", "drawing": A})).refusal is not None

    def test_opening_another_drawing_is_not_news(self):
        assert judge(A, A, MARK, 1234, history({"kind": "opened", "drawing": B})).refusal is None

    def test_a_bare_name_never_stands_for_a_file_elsewhere(self):
        # A folder check opens and closes D:\F\Drawing1.dwg while an unsaved Drawing1 is checked.
        other = r"D:\F\Drawing1.dwg"
        events = history({"kind": "opened", "drawing": other}, {"kind": "closed", "drawing": other})
        assert judge("Drawing1.dwg", "Drawing1.dwg", MARK, 1234, events) == Verdict(seen=6)

    def test_a_save_as_then_closed_needs_a_new_check(self):
        renamed = r"C:\jobs\a-rev2.dwg"
        events = history({"kind": "saved", "drawing": renamed, "was": A}, {"kind": "closed", "drawing": renamed})
        assert "a-rev2.dwg was closed" in judge(A, renamed, MARK, 1234, events).refusal

    def test_a_save_as_of_another_drawing_is_not_followed(self):
        events = history({"kind": "saved", "drawing": r"C:\x.dwg", "was": B})
        verdict = judge(A, r"C:\x.dwg", MARK, 1234, events)
        assert verdict.follow is None and verdict.refusal is None  # the name compare then refuses

    def test_a_plain_save_changes_nothing(self):
        assert judge(A, A, MARK, 1234, history({"kind": "saved", "drawing": A})) == Verdict(seen=5)

    def test_events_from_before_the_check_do_not_count(self):
        old = {"epoch": "e1", "seq": 4, "lost": False, "events": [{"seq": 3, "kind": "closed", "drawing": A}]}
        assert judge(A, A, MARK, 1234, old) == Verdict(seen=4)

    def test_with_history_dropped_off_what_is_left_is_still_judged(self):
        # e.g. a folder check of 60 drawings, then the checked one closed and opened again
        verdict = judge(A, A, MARK, 1234, history({"kind": "closed", "drawing": A}, lost=True))
        assert "closed" in verdict.refusal

    def test_with_history_dropped_off_nothing_is_followed_and_the_mark_stays(self):
        renamed = r"C:\jobs\a-rev2.dwg"
        lost = history({"kind": "saved", "drawing": renamed, "was": A}, lost=True)
        assert judge(A, renamed, MARK, 1234, lost) == Verdict()

    def test_names_compare_like_the_plugin(self):
        assert same(A, r"c:\JOBS\A.dwg")
        assert same("Drawing1.dwg", r"C:\x\Drawing1.dwg")
        assert not same(A, r"C:\other\a.dwg")
        assert not same("", A)
        assert short(A) == "a.dwg" and short("") == "no drawing"


# --- the bridge client ---------------------------------------------------------


def drawings_reply(**extra):
    return {
        "ok": True, "known": True, "epoch": "e1", "seq": 7, "active": A, "lost": False,
        "events": [{"seq": 7, "kind": "saved", "drawing": B, "was": A, "at": "10:02:03"}], **extra,
    }  # fmt: skip


class TestBridgeDrawingEvents:
    def test_the_reply_is_read(self, monkeypatch):
        seen = {}

        def call(self, op, **kw):
            seen.update(op=op, **kw)
            return drawings_reply()

        monkeypatch.setattr(Bridge, "call", call)
        found = Bridge(1).drawing_events(4)
        assert seen == {"op": "drawings", "since": 4}
        assert found == {
            "epoch": "e1", "seq": 7, "active": A, "lost": False,
            "events": [{"seq": 7, "kind": "saved", "drawing": B, "was": A, "at": "10:02:03"}],
        }  # fmt: skip

    def test_an_older_plugin_cannot_tell(self, monkeypatch):
        old = {"ok": False, "refusedBy": "BadRequest", "message": "does not know the request 'drawings'"}
        monkeypatch.setattr(Bridge, "call", lambda self, op, **kw: old)
        assert Bridge(1).drawing_events(0) is None
        assert Bridge(1).drawing_mark() is None

    def test_a_plugin_without_a_log_cannot_tell(self, monkeypatch):
        monkeypatch.setattr(Bridge, "call", lambda self, op, **kw: {"ok": True, "known": False})
        assert Bridge(1).drawing_events(0) is None

    def test_not_reachable_cannot_tell(self, monkeypatch):
        def refuse(self, op, **kw):
            raise BridgeRefused("AutoCAD is not connected to Heron.")

        monkeypatch.setattr(Bridge, "call", refuse)
        assert Bridge(1).drawing_events(0) is None

    def test_the_mark_is_the_epoch_and_the_newest_number(self, monkeypatch):
        seen = {}

        def call(self, op, **kw):
            seen.update(kw)
            return drawings_reply(events=[])

        monkeypatch.setattr(Bridge, "call", call)
        assert Bridge(1).drawing_mark() == ("e1", 7)
        assert seen["since"] == bridge_module.LATEST

    def test_unknown_front_is_none(self, monkeypatch):
        monkeypatch.setattr(Bridge, "call", lambda self, op, **kw: drawings_reply(active=None))
        assert Bridge(1).drawing_events(0)["active"] is None


# --- through the gate ---------------------------------------------------------


class Plugin:
    """A stand-in plug-in with a drawing log."""

    log: dict | None = None
    asked: list = []

    def __init__(self, pid):
        self.pid = pid

    def begin(self, tool, risk, summary, drawing):
        return "job1", False

    def find(self):
        return {"pipeName": "p", "token": "t"}

    def end(self, *args):
        pass

    def changes(self, job):
        return None

    def dialogs(self, job):
        return []

    def drawing_events(self, since):
        Plugin.asked.append(since)
        return Plugin.log

    def drawing_mark(self):
        return ("e1", 4) if Plugin.log is not None else None


@pytest.fixture
def plugged(monkeypatch):
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "on")
    state = {"drawing": A, "pid": 1234}
    Plugin.log = history()
    Plugin.asked = []

    async def probe():
        return state["pid"], state["drawing"]

    monkeypatch.setattr(gate, "Bridge", Plugin)
    monkeypatch.setattr(gate, "_probe", probe)
    gate.reset(looked_at=A, mark=MARK)
    yield state
    gate.reset()


def change(name="autocad_draw_line"):
    async def tool() -> str:
        connection.mark_writing()
        return '{"created": true, "handle": "2A"}'

    tool.__name__ = name
    return asyncio.run(tool_errors(tool)())


def test_a_change_with_nothing_happened_goes_ahead(plugged):
    assert "REFUSED" not in change()
    assert Plugin.asked == [MARK.seq]


def test_the_mark_moves_up_to_what_was_judged(plugged):
    Plugin.log = history({"kind": "activated", "drawing": B}, {"kind": "activated", "drawing": A})
    assert "REFUSED" not in change()
    assert gate._checked_mark == Mark(1234, "e1", 6)
    Plugin.log = history()
    change()
    assert Plugin.asked[-1] == 6


def test_a_refused_change_leaves_the_mark(plugged):
    Plugin.log = history({"kind": "closed", "drawing": A}, {"kind": "opened", "drawing": A})
    change()
    assert gate._checked_mark == MARK


def test_a_drawing_closed_and_opened_again_is_refused(plugged):
    Plugin.log = history({"kind": "closed", "drawing": A}, {"kind": "opened", "drawing": A})
    result = change()
    assert result.startswith("REFUSED")
    assert "closed at 10:00:00 and opened again" in result


def test_a_restarted_autocad_is_refused(plugged):
    Plugin.log = history(epoch="new")
    assert "started again" in change()


def test_a_save_as_is_followed_and_the_change_goes_ahead(plugged):
    renamed = r"C:\jobs\a-rev2.dwg"
    Plugin.log = history({"kind": "saved", "drawing": renamed, "was": A})
    plugged["drawing"] = renamed
    assert "REFUSED" not in change()
    assert gate._last_drawing == renamed


def test_without_the_events_a_save_as_is_still_a_switch(plugged):
    Plugin.log = None  # an older plug-in
    plugged["drawing"] = r"C:\jobs\a-rev2.dwg"
    assert "The active drawing changed from" in change()


def test_an_older_plugin_leaves_the_guard_as_it_was(plugged):
    Plugin.log = None
    assert "REFUSED" not in change()


def test_reads_and_views_never_ask(plugged):
    async def read() -> str:
        return "{}"

    read.__name__ = "autocad_list_layers"
    asyncio.run(tool_errors(read)())
    assert Plugin.asked == []


def test_status_marks_where_the_log_stands(plugged):
    gate.reset()

    async def status() -> str:
        return '{"connected": true}'

    status.__name__ = "autocad_status"
    asyncio.run(tool_errors(status)())
    assert gate._last_drawing == A
    assert gate._checked_mark == Mark(1234, "e1", 4)


def test_status_takes_its_mark_before_its_work(plugged, monkeypatch):
    # A close during the status call must not be swallowed by a mark taken after it.
    gate.reset()
    marks = iter([("e1", 4), ("e1", 9)])
    monkeypatch.setattr(Plugin, "drawing_mark", lambda self: next(marks))

    async def status() -> str:
        return '{"connected": true}'

    status.__name__ = "autocad_status"
    asyncio.run(tool_errors(status)())
    assert gate._checked_mark == Mark(1234, "e1", 4)


def test_a_new_drawing_takes_its_mark_after_its_work(plugged, monkeypatch):
    gate.reset()
    marks = iter([("e1", 9)])
    monkeypatch.setattr(Plugin, "drawing_mark", lambda self: next(marks))

    async def create() -> str:
        connection.mark_writing()
        return '{"created": true}'

    create.__name__ = "autocad_create_drawing"
    asyncio.run(tool_errors(create)())
    assert gate._checked_mark == Mark(1234, "e1", 9)


def test_status_with_an_older_plugin_has_no_mark(plugged):
    gate.reset()
    Plugin.log = None

    async def status() -> str:
        return '{"connected": true}'

    status.__name__ = "autocad_status"
    asyncio.run(tool_errors(status)())
    assert gate._last_drawing == A and gate._checked_mark is None
