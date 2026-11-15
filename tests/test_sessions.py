"""Which AutoCAD Heron works in, when several are open (D-49, no AutoCAD).

COM hands the server whichever AutoCAD registered first. With one AutoCAD
connected to Heron, that one is used; with two, nothing is sent until the
chat picks one; a picked one that closes stops Heron, which never moves on
to another by itself.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.core import connection, gate, sessions
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import document


def acad(pid: int, version: str = "25.1") -> dict:
    return {"pid": pid, "acad_version": version, "plugin_version": "1.5.0", "protocol_version": 1,
            "connected_since": "2026-11-15T08:00:00Z"}  # fmt: skip


@pytest.fixture
def autocads(monkeypatch):
    """The AutoCADs whose Heron button is pressed: edit the list in a test."""
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "on")
    found: list[dict] = []
    from autocad_mcp.core import diagnose

    monkeypatch.setattr(diagnose, "connected_autocads", lambda folder=None: list(found))
    monkeypatch.setattr(sessions, "FRESH", 0.0)
    sessions.forget()
    yield found
    sessions.forget()


def test_none_connected_takes_coms_own_choice(autocads):
    assert sessions.target() is None


def test_one_connected_is_the_one_used(autocads):
    autocads.append(acad(1111))
    assert sessions.target() == 1111


def test_two_connected_and_none_picked_sends_nothing(autocads):
    autocads.extend([acad(1111, "24.3"), acad(2222, "25.1")])
    with pytest.raises(AutocadError) as caught:
        sessions.target()
    words = str(caught.value)
    assert "2 AutoCADs are connected" in words and "1111" in words and "2222" in words
    assert "autocad_use_autocad" in words and words.endswith("Nothing was sent to AutoCAD.")


def test_a_picked_one_is_used_while_it_stays_connected(autocads):
    autocads.extend([acad(1111), acad(2222)])
    sessions.choose(2222)
    assert sessions.target() == 2222


def test_a_picked_one_that_closes_stops_heron_and_never_moves_on(autocads):
    autocads.extend([acad(1111), acad(2222)])
    sessions.choose(2222)
    autocads.pop()
    with pytest.raises(AutocadError) as caught:
        sessions.target()
    assert "never moves on" in str(caught.value)


def test_picking_one_that_is_not_connected_is_refused(autocads):
    autocads.append(acad(1111))
    with pytest.raises(AutocadError) as caught:
        sessions.choose(9999)
    assert "1111" in str(caught.value)
    assert sessions.chosen() is None


def test_with_the_bridge_off_nothing_changes(autocads, monkeypatch):
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "off")
    autocads.extend([acad(1111), acad(2222)])
    assert sessions.target() is None


def test_use_autocad_needs_no_padlock():
    assert risk_of("autocad_use_autocad") is Risk.READ
    assert "autocad_use_autocad" in gate.SESSION_TOOLS


def test_use_autocad_lists_then_picks_and_asks_for_units_again(autocads, monkeypatch):
    autocads.extend([acad(1111, "24.3"), acad(2222, "25.1")])
    gate.reset(r"C:\a.dwg")
    listed = json.loads(asyncio.run(document.autocad_use_autocad()))
    assert listed["in_use"] is None and [a["pid"] for a in listed["connected"]] == [1111, 2222]
    assert "ask the modeller which" in listed["note"]
    picked = json.loads(asyncio.run(document.autocad_use_autocad(pid=2222)))
    assert picked["in_use"] == 2222 and "autocad_status" in picked["note"]
    assert gate._last_drawing is None  # the other AutoCAD's units are checked again


def test_use_autocad_answers_when_the_gate_cannot_tell_which(autocads, monkeypatch):
    """The one tool that must work exactly when two are connected and none is picked."""
    autocads.extend([acad(1111), acad(2222)])

    async def ambiguous():
        sessions.target()  # raises: two connected
        return 0, ""

    monkeypatch.setattr(gate, "_probe", ambiguous)
    listed = json.loads(asyncio.run(document.autocad_use_autocad()))
    assert len(listed["connected"]) == 2


# ---------------------------------------------------------------------------
# The COM side: reaching that AutoCAD
# ---------------------------------------------------------------------------


class App:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.Documents = type("Docs", (), {"Count": 1})()


def test_the_cache_drops_a_pointer_to_the_wrong_autocad(autocads, monkeypatch):
    autocads.append(acad(2222))
    reached = []

    def dispatch(self, launch_if_needed, target=None):
        reached.append(target)
        return App(target)

    monkeypatch.setattr(connection._AppCache, "_dispatch", dispatch)
    cache = connection._AppCache()
    cache.app, cache.pid = App(1111), 1111
    assert cache.get().pid == 2222
    assert reached == [2222]
    assert cache.get().pid == 2222 and reached == [2222]  # kept while it is the right one


def test_coms_first_choice_is_used_when_it_is_the_one(monkeypatch):
    first = App(2222)
    monkeypatch.setattr(connection.win32com.client, "GetActiveObject", lambda prog: first)
    monkeypatch.setattr(connection, "_pid_of", lambda app: app.pid)
    monkeypatch.setattr(connection, "_app_of_process", lambda pid: pytest.fail("no search needed"))
    assert connection._AppCache()._dispatch(False, 2222) is first


def test_the_second_autocad_is_found_through_its_drawings(monkeypatch):
    second = App(2222)
    monkeypatch.setattr(connection.win32com.client, "GetActiveObject", lambda prog: App(1111))
    monkeypatch.setattr(connection, "_pid_of", lambda app: app.pid)
    monkeypatch.setattr(connection, "_app_of_process", lambda pid: second if pid == 2222 else None)
    assert connection._AppCache()._dispatch(False, 2222) is second


def test_an_autocad_with_no_saved_drawing_cannot_be_reached_and_says_why(monkeypatch):
    monkeypatch.setattr(connection.win32com.client, "GetActiveObject", lambda prog: App(1111))
    monkeypatch.setattr(connection, "_pid_of", lambda app: app.pid)
    monkeypatch.setattr(connection, "_app_of_process", lambda pid: None)
    with pytest.raises(AutocadError) as caught:
        connection._AppCache()._dispatch(False, 2222)
    assert "saved drawings" in str(caught.value) and "Nothing was sent" in str(caught.value)
