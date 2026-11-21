"""The padlocks come from the connected AutoCAD's memory, not from a file (D-59, D-60). No AutoCAD.

Since plug-in 1.6.0 the padlocks live only in AutoCAD's memory, so the
server asks the plug-in (its ping answer) instead of reading
heron-autocad.config. autocad_why uses that answer, and says when a Windows
policy holds a padlock off.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.acad import why
from autocad_mcp.core import bridge, diagnose, gate, sessions
from autocad_mcp.core.bridge import Bridge, BridgeRefused
from autocad_mcp.core.risk import RISK, Risk
from autocad_mcp.tools import explain, register_all, resources

register_all()
ENTRIES = asyncio.run(resources._entries())


def ping_reply(changes=False, publish=False, admin=False, ask=False, held=()):
    return {
        "ok": True,
        "protocolVersion": 1,
        "stopped": False,
        "padlocks": {"changes": changes, "publish": publish, "admin": admin, "askToKeep": ask},
        "held": {name: name in held for name in ("changes", "publish", "admin")},
    }


class TestBridgePadlocks:
    def test_the_ping_answer_is_read(self, monkeypatch):
        monkeypatch.setattr(Bridge, "call", lambda self, op, **kw: ping_reply(changes=True, held=("publish",)))
        locks = Bridge(4242).padlocks()
        assert locks == {"changes": True, "publish": False, "admin": False, "ask_to_keep": False,
                         "held": ["publish"]}  # fmt: skip

    def test_an_older_plug_in_cannot_tell(self, monkeypatch):
        monkeypatch.setattr(Bridge, "call", lambda self, op, **kw: {"ok": True, "protocolVersion": 1, "stopped": False})
        assert Bridge(4242).padlocks() is None

    def test_an_autocad_that_does_not_answer_cannot_tell(self, monkeypatch):
        def refuse(self, op, **kw):
            raise BridgeRefused("AutoCAD is not connected to Heron.")

        monkeypatch.setattr(Bridge, "call", refuse)
        assert Bridge(4242).padlocks() is None

    def test_only_true_counts_as_on(self, monkeypatch):
        reply = ping_reply()
        reply["padlocks"]["changes"] = "true"
        monkeypatch.setattr(Bridge, "call", lambda self, op, **kw: reply)
        assert Bridge(4242).padlocks()["changes"] is False


def connected(*pids):
    return {"autocads_connected": [{"pid": pid} for pid in pids]}


class TestWhichAutocad:
    @pytest.fixture(autouse=True)
    def asked(self, monkeypatch):
        seen = []
        monkeypatch.setattr(bridge, "bridge_enabled", lambda: True)
        monkeypatch.setattr(explain, "bridge_enabled", lambda: True)
        monkeypatch.setattr(Bridge, "padlocks", lambda self: seen.append(self.pid) or {"changes": True})
        return seen

    def test_the_only_one_connected(self, asked):
        assert explain.padlocks_now(connected(7), None) == {"changes": True}
        assert asked == [7]

    def test_the_one_this_chat_picked(self, asked):
        explain.padlocks_now(connected(7, 8), 8)
        assert asked == [8]

    def test_several_and_none_picked_asks_none(self, asked):
        assert explain.padlocks_now(connected(7, 8), None) is None
        assert asked == []

    def test_nothing_connected_asks_none(self, asked):
        assert explain.padlocks_now(connected(), None) is None
        assert asked == []

    def test_without_the_bridge_asks_none(self, asked, monkeypatch):
        monkeypatch.setattr(explain, "bridge_enabled", lambda: False)
        assert explain.padlocks_now(connected(7), None) is None


def explain_with(padlocks, job="run this autolisp"):
    report = {"plugin_installed": "1.6.0", "checks": [], "padlocks": padlocks,
              "autocads_connected": [{"pid": 4242, "acad_version": "26.0", "plugin_version": "1.6.0",
                                      "protocol_version": 1}]}  # fmt: skip
    return why.explain(
        job, entries=ENTRIES, level_of=lambda tool: RISK.get(tool, Risk.ADMIN), descriptions={},
        known_tools=set(RISK), report=report, bridge_on=True, chosen_pid=None, drawing_checked=True,
    )  # fmt: skip


class TestWhyHeld:
    def test_a_held_padlock_names_the_policy_not_the_command(self):
        answer = explain_with({"changes": True, "publish": False, "admin": False, "held": ["admin"]})
        names = [r["reason"] for r in answer["reasons"]]
        assert "admin_held" in names and "admin_off" not in names
        held = next(r for r in answer["reasons"] if r["reason"] == "admin_held")
        assert "Windows policy" in held["says"]
        assert "administrator" in held["what_to_do"] and "HERONADMIN" not in held["what_to_do"]
        assert answer["can_run"] is False

    def test_a_padlock_off_but_not_held_still_names_the_command(self):
        answer = explain_with({"changes": True, "publish": False, "admin": False, "held": []})
        off = next(r for r in answer["reasons"] if r["reason"] == "admin_off")
        assert "HERONADMIN" in off["what_to_do"]

    def test_all_on_from_the_plug_in_means_it_should_run(self):
        answer = explain_with({"changes": True, "publish": True, "admin": True, "held": []})
        assert answer["can_run"] is True


def test_the_tool_asks_the_connected_autocad(monkeypatch):
    monkeypatch.setattr(diagnose, "report", lambda: {
        "plugin_installed": "1.6.0", "checks": [],
        "autocads_connected": [{"pid": 4242, "acad_version": "26.0", "plugin_version": "1.6.0", "protocol_version": 1}],
    })  # fmt: skip
    monkeypatch.setattr(explain, "bridge_enabled", lambda: True)
    monkeypatch.setattr(sessions, "chosen", lambda: None)
    monkeypatch.setattr(Bridge, "padlocks", lambda self: {"changes": True, "publish": True, "admin": True, "held": []})
    gate.reset()
    answer = json.loads(asyncio.run(explain.autocad_why("draw a line from 0,0 to 100,0")))
    assert not [r for r in answer["reasons"] if r["reason"].endswith("_off")]
