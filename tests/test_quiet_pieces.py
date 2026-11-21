"""A batch through the plug-in leaves fewer Command: prompts (#45, D-98). No AutoCAD.

Every top-level expression typed into AutoCAD leaves one "Command:" prompt in
the history, echo off or not: about 27 for 41 objects (live, 2026-10-26).
The 600-character pieces were measured for COM SendCommand. The plug-in now
says in its ping how long a line it types (quietLimit, 1,500), and the batch
goes through it in pieces up to that, the short set-up pieces packed
together. Over COM, and for an older plug-in, the pieces stay as they were.
"""

from __future__ import annotations

import asyncio
import json
import re

import pytest

from autocad_mcp.acad.lisp import (
    CHUNK_LIMIT,
    QUIET_CHUNK_LIMIT,
    build_chunks,
    pack,
    parse_output,
    quiet_pieces,
)
from autocad_mcp.core import bridge as bridge_module
from autocad_mcp.core import gate
from autocad_mcp.core.bridge import NOTHING_SENT, Bridge
from autocad_mcp.core.registry import tool_errors
from autocad_mcp.tools import batch

OUT = r"C:\temp\out.txt"


def forty_one() -> list[list[str]]:
    """A batch like the live check's 41 objects: lines, circles, labels and outlines."""
    ops = []
    for i in range(14):
        ops.append({"type": "line", "start": [i * 1000, 0], "end": [i * 1000, 5000], "layer": "M-GRID"})
    for i in range(10):
        ops.append({"type": "circle", "center": [i * 1000, 2500], "radius": 150, "layer": "M-EQPT"})
    for i in range(10):
        ops.append({"type": "text", "position": [i * 1000, 5200], "text": f"AHU-{i:02d}", "height": 250, "layer": "M-ANNO"})
    for i in range(7):
        ops.append({"type": "polyline", "points": [[i * 1000, 0], [i * 1000 + 600, 0], [i * 1000 + 600, 400], [i * 1000, 400]],
                    "closed": True, "layer": "M-DUCT"})  # fmt: skip
    return [batch.BUILDERS[op["type"]](op, n) for n, op in enumerate(ops)]


def balanced(text: str) -> bool:
    depth = 0
    for ch in re.sub(r'"(?:[^"\\]|\\.)*"', '""', text):
        depth += (ch == "(") - (ch == ")")
        if depth < 0:
            return False
    return depth == 0


def entmakes(pieces: list[str]) -> list[str]:
    """Every entmake, in the order AutoCAD would run them."""
    return re.findall(r"\(entmake \(list .*?\)\) \(write-line", " ".join(pieces))


# --- the pieces --------------------------------------------------------------


def test_fewer_pieces_than_over_com_for_the_live_checks_batch():
    entities = forty_one()
    com = build_chunks(entities, True, OUT)
    plugin = quiet_pieces(entities, True, OUT, QUIET_CHUNK_LIMIT)
    assert len(com) >= 15  # one prompt each: what the live check saw
    assert len(plugin) <= len(com) // 2
    assert len(plugin) <= 10


def test_every_piece_fits_the_plugins_line_and_is_balanced():
    for limit in (900, 1200, QUIET_CHUNK_LIMIT):
        for piece in quiet_pieces(forty_one(), True, OUT, limit):
            assert len(piece) <= limit
            assert balanced(piece)


def test_a_plugin_saying_more_still_gets_no_more_than_heron_sends():
    pieces = quiet_pieces(forty_one(), True, OUT, 100_000)
    assert max(len(p) for p in pieces) <= QUIET_CHUNK_LIMIT


def test_a_plugin_saying_less_than_com_gets_the_com_size():
    assert max(len(p) for p in quiet_pieces(forty_one(), True, OUT, 100)) <= CHUNK_LIMIT


def test_the_same_objects_in_the_same_order_as_over_com():
    entities = forty_one()
    assert entmakes(quiet_pieces(entities, True, OUT, QUIET_CHUNK_LIMIT)) == entmakes(build_chunks(entities, True, OUT))
    assert len(entmakes(build_chunks(entities, True, OUT))) == 41


def test_the_helper_comes_before_its_first_use_and_the_finish_stays_alone():
    pieces = quiet_pieces(forty_one(), True, OUT, QUIET_CHUNK_LIMIT)
    first = pieces[0]
    assert first.index("(defun heron-run") < first.index("(vla-startundomark")
    finish = build_chunks(forty_one(), True, OUT)[-1]
    assert pieces[-1] == finish  # an error before it can never leave the undo group open
    assert all('"DONE"' not in piece for piece in pieces[:-1])


def test_a_small_batch_is_two_prompts():
    pieces = quiet_pieces(forty_one()[:3], True, OUT, QUIET_CHUNK_LIMIT)
    assert len(pieces) == 2


def test_every_piece_returns_nothing_to_print():
    for piece in quiet_pieces(forty_one(), False, OUT, QUIET_CHUNK_LIMIT):
        assert piece.startswith("(progn ") and piece.endswith("(princ))") or piece.startswith("(heron-run "), piece[:60]


def test_a_long_polyline_is_still_built_up_in_pieces():
    from autocad_mcp.acad.lisp import dotted, lisp_string

    pairs = [dotted(0, lisp_string("LWPOLYLINE"))] + [dotted(10, f"(list {i}.0 {i}.0)") for i in range(800)]
    pieces = quiet_pieces([pairs], True, OUT, QUIET_CHUNK_LIMIT)
    assert all(len(p) <= QUIET_CHUNK_LIMIT for p in pieces)
    assert " ".join(pieces).count("(entmake") == 1
    assert len(pieces) < len(build_chunks([pairs], True, OUT))


def test_pack_keeps_order_and_leaves_a_long_piece_alone():
    assert pack(["(a)", "(b)", "(c)"], 100) == ["(progn (a) (b) (c) (princ))"]
    long = "(" + "x" * 50 + ")"
    assert pack(["(a)", long, "(b)"], 40) == ["(a)", long, "(b)"]
    assert pack([], 100) == []


# --- what came back ----------------------------------------------------------


def test_results_missing_with_done_written_are_never_a_quiet_success():
    out = parse_output("1A\n1B\nDONE\n", expected=5)
    assert out["missing"] == 3
    assert out["completed"] is True
    assert "3 operation(s) never reached AutoCAD" in out["hint"]


def test_a_full_batch_has_nothing_missing():
    out = parse_output("1A\n1B\nDONE\n", expected=2)
    assert "missing" not in out and "hint" not in out


def test_an_error_or_no_done_is_said_as_before():
    assert "missing" not in parse_output("1A\nERROR bad argument\n", expected=5)
    assert "missing" not in parse_output("1A\n", expected=5)


# --- through the batch tool --------------------------------------------------


class FakeDoc:
    def __init__(self):
        self.sent: list[str] = []
        self.out = None

    def GetVariable(self, name):
        return 0

    def run(self, text):
        found = re.search(r'\(open "([^"]+)" "w"\)', text)
        if found:
            self.out = found.group(1)
        if '"DONE"' in text and self.out:
            with open(self.out, "w") as fh:
                fh.write("2A\n2B\nDONE\n")

    def SendCommand(self, text):
        self.sent.append(text)
        self.run(text)


def typing(typed: list[list[str]]):
    """A plug-in that takes the lines, and AutoCAD running them."""

    def make(doc: FakeDoc):
        def sender(lines):
            typed.append(list(lines))
            doc.run(" ".join(lines))
            return True

        return sender

    return make


def draw(monkeypatch, make_sender, limit):
    """make_sender(doc) gives the quiet sender, or None for no plug-in."""
    doc = FakeDoc()
    sender = make_sender(doc) if make_sender else None

    async def run(fn):
        return fn()

    monkeypatch.setattr(batch, "run", run)
    monkeypatch.setattr(batch, "get_doc", lambda: doc)
    monkeypatch.setattr(batch, "require_idle", lambda d: None)
    monkeypatch.setattr(batch, "ensure_layer", lambda d, name: (None, False))
    monkeypatch.setattr(batch, "quiet_sender", lambda: sender)
    monkeypatch.setattr(batch, "quiet_limit", lambda: limit)
    ops = [{"type": "line", "start": [i, 0], "end": [i, 100]} for i in range(40)] + [{"type": "point", "position": [0, 0]}]
    result = json.loads(asyncio.run(batch.autocad_batch_draw(operations=ops)))
    return doc, result


def test_through_the_plugin_the_batch_goes_in_its_longer_pieces(monkeypatch):
    typed: list[list[str]] = []
    doc, result = draw(monkeypatch, typing(typed), 1500)
    assert result["completed"] is True
    pieces = typed[0]
    assert doc.sent == []  # nothing over COM
    assert max(len(p) for p in pieces) <= 1500
    assert max(len(p) for p in pieces) > CHUNK_LIMIT
    over_com = len(build_chunks([batch.BUILDERS["line"]({"start": [0, 0], "end": [0, 1]}, 0)] * 40
                                + [batch.BUILDERS["point"]({"position": [0, 0]}, 40)], True, OUT))  # fmt: skip
    assert len(pieces) < over_com / 2


def test_an_older_plugin_gets_the_com_pieces_quietly(monkeypatch):
    typed: list[list[str]] = []
    doc, _ = draw(monkeypatch, typing(typed), None)
    assert max(len(p) for p in typed[0]) <= CHUNK_LIMIT
    assert doc.sent == []


def test_when_the_plugin_says_no_com_sends_the_short_pieces(monkeypatch):
    doc, result = draw(monkeypatch, lambda doc: (lambda lines: False), 1500)
    assert doc.sent and max(len(s) for s in doc.sent) <= CHUNK_LIMIT + 1
    assert result["completed"] is True


def test_without_the_plugin_nothing_asks_for_its_limit(monkeypatch):
    asked = []
    monkeypatch.setattr(batch, "quiet_limit", lambda: asked.append(1))
    doc = FakeDoc()

    async def run(fn):
        return fn()

    monkeypatch.setattr(batch, "run", run)
    monkeypatch.setattr(batch, "get_doc", lambda: doc)
    monkeypatch.setattr(batch, "require_idle", lambda d: None)
    monkeypatch.setattr(batch, "ensure_layer", lambda d, name: (None, False))
    monkeypatch.setattr(batch, "quiet_sender", lambda: None)
    asyncio.run(batch.autocad_batch_draw(operations=[{"type": "point", "position": [0, 0]}]))
    assert asked == []
    assert doc.sent and max(len(s) for s in doc.sent) <= CHUNK_LIMIT + 1


# --- the bridge client ------------------------------------------------------


# Looked up on the module at each use: test_bridge reloads it, which makes new classes.
def refused():
    return bridge_module.BridgeRefused


@pytest.fixture
def piped(monkeypatch):
    """Bridge._request and _exchange stood in for: what the pipe answers, or how it fails."""
    state: dict = {"reply": {"ok": True}, "raise": None, "requests": []}
    monkeypatch.setattr(Bridge, "_request", lambda self, op, fields: ("pipe", {"op": op, **fields}))

    def exchange(pipe, request, timeout):
        state["requests"].append(request)
        if state["raise"] is not None:
            raise state["raise"]
        return state["reply"]

    monkeypatch.setattr(bridge_module, "_exchange", exchange)
    return state


def test_taken_lines_are_true(piped):
    assert Bridge(1).send_quiet("j1", ["(a)"]) is True
    assert piped["requests"][0] == {"op": "send_quiet", "job": "j1", "lines": ["(a)"]}


def test_a_pipe_that_would_not_open_is_false_so_com_sends_them(piped):
    piped["raise"] = bridge_module.PipeUnavailable("gone")
    assert Bridge(1).send_quiet("j1", ["(a)"]) is False


def test_a_request_sent_and_never_answered_is_never_typed_again(piped):
    piped["raise"] = TimeoutError()
    assert Bridge(1).send_quiet("j1", ["(a)"]) is True
    piped["raise"] = OSError("Heron in AutoCAD closed the connection")
    assert Bridge(1).send_quiet("j1", ["(a)"]) is True


def test_a_line_too_long_for_the_plugin_is_false_so_com_sends_short_ones(piped):
    piped["reply"] = {"ok": False, "refusedBy": "TooLong", "message": "too long. " + NOTHING_SENT}
    assert Bridge(1).send_quiet("j1", ["(a)"]) is False


def test_another_drawing_in_front_ends_the_input_never_sent_over_com(piped):
    words = ("The drawing in front changed while this job ran: it began in a.dwg, and b.dwg is in front now, "
             "so Heron typed none of this input. What the job did before it stays.")  # fmt: skip
    piped["reply"] = {"ok": False, "refusedBy": "Drawing", "message": words}
    with pytest.raises(refused()) as caught:
        Bridge(1).send_quiet("j1", ["(a)"])
    # Not "nothing was sent": the job may have made layers before it.
    assert str(caught.value) == words


def test_input_autocad_never_got_to_ends_the_input(piped):
    piped["reply"] = {"ok": False, "refusedBy": "NotStarted", "message": "AutoCAD did not get to this input within 10 s"}
    with pytest.raises(refused()):
        Bridge(1).send_quiet("j1", ["(a)"])


def test_the_stop_still_says_nothing_was_sent(piped):
    piped["reply"] = {"ok": False, "refusedBy": "Stopped", "message": "The modeller stopped Heron in AutoCAD (HERONSTOP)."}
    with pytest.raises(refused()) as caught:
        Bridge(1).send_quiet("j1", ["(a)"])
    assert str(caught.value).endswith(NOTHING_SENT)


def test_typing_that_went_wrong_part_way_is_never_typed_again(piped):
    piped["reply"] = {"ok": True, "unknown": True}
    assert Bridge(1).send_quiet("j1", ["(a)"]) is True


def test_the_wait_is_longer_than_the_plugins(piped, monkeypatch):
    seen = {}

    def exchange(pipe, request, timeout):
        seen["timeout"] = timeout
        return {"ok": True}

    monkeypatch.setattr(bridge_module, "_exchange", exchange)
    Bridge(1).send_quiet("j1", ["(a)"])
    assert seen["timeout"] > 10


def test_not_connected_is_false(monkeypatch):
    def refuse(self, op, fields):
        raise refused()("AutoCAD is not connected to Heron.")

    monkeypatch.setattr(Bridge, "_request", refuse)
    assert Bridge(1).send_quiet("j1", ["(a)"]) is False


@pytest.mark.parametrize(
    ("reply", "limit"),
    [
        ({"ok": True, "quietLimit": 1500}, 1500),
        ({"ok": True}, None),  # an older plug-in
        ({"ok": True, "quietLimit": True}, None),
        ({"ok": True, "quietLimit": "1500"}, None),
        ({"ok": True, "quietLimit": 0}, None),
        ({"ok": False, "quietLimit": 1500}, None),
    ],
)
def test_the_limit_comes_from_the_ping(monkeypatch, reply, limit):
    monkeypatch.setattr(Bridge, "call", lambda self, op, **kw: reply)
    assert Bridge(1).quiet_limit() == limit


def test_the_limit_cannot_be_asked_when_not_reachable(monkeypatch):
    def refuse(self, op, **kw):
        raise refused()("no")

    monkeypatch.setattr(Bridge, "call", refuse)
    assert Bridge(1).quiet_limit() is None


# --- the gate -----------------------------------------------------------------


def test_the_limit_is_asked_only_inside_a_job(monkeypatch):
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "on")

    class Plugin:
        def __init__(self, pid):
            pass

        def begin(self, *args):
            return "job1", False

        def find(self):
            return {"pipeName": "p", "token": "t"}

        def end(self, *args):
            pass

        def changes(self, job):
            return None

        def dialogs(self, job):
            return []

        def quiet_limit(self):
            return 1500

    async def probe():
        return 1, r"C:\a.dwg"

    monkeypatch.setattr(gate, "Bridge", Plugin)
    monkeypatch.setattr(gate, "_probe", probe)
    gate.reset(looked_at=r"C:\a.dwg")
    assert gate.quiet_limit() is None
    seen = {}

    async def tool() -> str:
        seen["limit"] = gate.quiet_limit()
        return "{}"

    tool.__name__ = "autocad_batch_draw"
    asyncio.run(tool_errors(tool)())
    gate.reset()
    assert seen["limit"] == 1500
