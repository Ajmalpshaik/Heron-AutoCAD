"""The Heron Companion page (D-71): a file per chat, rewritten after every job, no server, no COM."""

from __future__ import annotations

import asyncio
import json
import os
import time

import pytest
import test_gate
from test_gate import make_tool

from autocad_mcp.acad.units import unit_name
from autocad_mcp.core import companion, gate
from autocad_mcp.tools import companion as tool

env = test_gate.env  # the gate with the bridge and COM faked


@pytest.fixture(autouse=True)
def fresh():
    companion.reset()
    yield
    companion.reset()


def test_the_page_escapes_everything_and_runs_no_script():
    state = {"version": "1.8.0", "conversation": "abc", "drawing": r"C:\<b>.dwg",
             "activity": [{"at": "10:00:00", "what": "<script>alert(1)</script>", "risk": "change",
                           "outcome": "done", "seconds": 0.2, "drawing": r"C:\x.dwg",
                           "changes": {"added": 2, "modified": 0, "erased": 1}}],
             "last_change": None}  # fmt: skip
    page = companion.render(state)
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "default-src 'none'" in page and 'http-equiv="refresh"' in page
    assert "+2 ~0 -1" in page and "C:\\&lt;b&gt;.dwg" in page


def test_one_page_per_chat_and_old_pages_are_tidied(tmp_path):
    old = companion.folder()
    old.mkdir(parents=True)
    stale = old / "heron-companion-oldchat.html"
    stale.write_text("x")
    week_ago = time.time() - 8 * 86400
    os.utime(stale, (week_ago, week_ago))
    path = companion.write({"conversation": "chat/../1", "activity": []})
    assert path.name == "heron-companion-chat1.html" and path.parent == old
    assert not stale.exists()


def test_the_gate_writes_the_page_only_once_the_chat_asked(env):
    draw, _ = make_tool("autocad_draw_line")
    asyncio.run(draw())
    page = companion.page_path(gate.companion_state()["conversation"])
    assert not page.exists()
    companion.start(None)
    asyncio.run(draw())
    text = page.read_text(encoding="utf-8")
    assert "draw line" in text.lower()
    companion.stop()
    page.unlink()
    asyncio.run(draw())
    assert not page.exists()


def test_writing_the_page_never_fails_a_job(env, monkeypatch):
    companion.start(None)
    monkeypatch.setattr(companion, "page_path", lambda conversation: (_ for _ in ()).throw(OSError("disk full")))
    draw, calls = make_tool("autocad_draw_line")
    assert asyncio.run(draw()).startswith("DONE")
    assert calls == [1]


class Selection:
    Count = 3

    def Item(self, i):
        return type("E", (), {"ObjectName": "AcDbLine" if i < 2 else "AcDbCircle"})()


class Doc:
    FullName = r"C:\Jobs\M-101.dwg"
    PickfirstSelectionSet = Selection()
    ActiveLayout = type("L", (), {"Name": "Model"})()

    def GetVariable(self, name):
        return {"INSUNITS": 4, "VIEWCTR": (1000.12345, 500.0, 0.0), "VIEWSIZE": 2500.0}[name]


def test_the_tool_reads_the_drawing_view_and_selection_once_and_opens_the_page(monkeypatch):
    async def now(fn):
        return fn()

    monkeypatch.setattr(tool, "run", now)
    monkeypatch.setattr(tool, "get_doc", Doc)
    result = json.loads(asyncio.run(tool.autocad_companion()))
    assert result["open"].startswith("file:")
    snap = result["snapshot"]
    assert snap["units"] == unit_name(4)
    assert snap["view"] == {"centre": [1000.123, 500.0], "height": 2500.0}
    assert snap["selection"] == {"count": 3, "types": {"Line": 2, "Circle": 1}}
    page = open(result["page"], encoding="utf-8").read()
    assert "M-101.dwg" in page and "2 Line, 1 Circle" in page
    assert companion.enabled()
    stopped = json.loads(asyncio.run(tool.autocad_companion(stop=True)))
    assert stopped["stopped"] is True and not companion.enabled()


def test_it_is_a_read_tool():
    from autocad_mcp.core.risk import Risk, risk_of

    assert risk_of("autocad_companion") is Risk.READ
