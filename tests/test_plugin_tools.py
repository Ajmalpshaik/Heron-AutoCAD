"""The tools the Heron plug-in does itself: 3D edits and super hatch (no AutoCAD).

COM has no call for loft, fillet edges, shell, press-pull, thicken or a
clipped block hatch, so these tools hand the work to the plug-in over the
bridge ("run", D-40). What is checked here is everything up to the pipe: what
each tool asks the plug-in for, in which units and directions, and how every
kind of answer comes back to the chat.
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest

from autocad_mcp.core import bridge, connection, gate
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import _shared, solid_edits, superhatch

# ---------------------------------------------------------------------------
# Bridge.run: the Python end of the "run" request
# ---------------------------------------------------------------------------


# test_bridge reloads the bridge module, which makes new classes: so every
# name here is looked up on the module when the test runs, never imported.


@pytest.fixture
def pipe(monkeypatch):
    """A plug-in that answers every request with ``pipe.reply``."""

    class Pipe:
        reply: dict = {"ok": True, "result": {}}
        error: BaseException | None = None
        sent: list = []
        timeouts: list = []

    state = Pipe()
    state.sent = []
    state.timeouts = []

    def exchange(name, request, timeout):
        state.sent.append(request)
        state.timeouts.append(timeout)
        if state.error is not None:
            raise state.error
        return state.reply

    monkeypatch.setattr(bridge.Bridge, "find", lambda self: {"pipeName": "heron.test", "token": "tok"})
    monkeypatch.setattr(bridge, "_exchange", exchange)
    return state


class TestBridgeRun:
    def test_it_sends_the_job_the_operation_and_its_arguments(self, pipe):
        pipe.reply = {"ok": True, "result": {"handle": "2A", "edges": [4, 5]}}
        result = bridge.Bridge(1).run("j1", "fillet_edges", {"handle": "2A", "radius": 5.0})
        assert result == {"handle": "2A", "edges": [4, 5]}
        request = pipe.sent[0]
        assert request["op"] == "run" and request["job"] == "j1" and request["token"] == "tok"
        assert request["operation"] == "fillet_edges" and request["args"] == {"handle": "2A", "radius": 5.0}

    def test_it_waits_long_enough_for_a_slow_model(self, pipe):
        bridge.Bridge(1).run("j1", "shell", {})
        assert pipe.timeouts[0] == bridge.RUN_TIMEOUT >= 120

    def test_autocads_refusal_comes_back_in_its_own_words(self, pipe):
        words = "AutoCAD would not round 4 edge(s) at radius 50 (InvalidInput). Nothing was changed."
        pipe.reply = {"ok": False, "refusedBy": "Operation", "message": words}
        with pytest.raises(AutocadError) as caught:
            bridge.Bridge(1).run("j1", "fillet_edges", {})
        assert str(caught.value) == words
        assert not isinstance(caught.value, bridge.BridgeRefused)

    def test_an_older_plug_in_says_to_update_it(self, pipe):
        pipe.reply = {
            "ok": False,
            "refusedBy": "BadRequest",
            "message": "Heron in AutoCAD does not know the request 'run'. Update Heron so both sides match. " + bridge.NOTHING_SENT,
        }
        with pytest.raises(bridge.BridgeRefused) as caught:
            bridge.Bridge(1).run("j1", "loft", {})
        text = str(caught.value)
        assert "1.2.0" in text and "build_plugin" in text and text.endswith(bridge.NOTHING_SENT)

    def test_a_job_refusal_says_nothing_was_sent(self, pipe):
        pipe.reply = {"ok": False, "refusedBy": "Job", "message": "Heron in AutoCAD only does its own operations inside a running job."}
        with pytest.raises(bridge.BridgeRefused) as caught:
            bridge.Bridge(1).run("j1", "loft", {})
        assert str(caught.value).endswith(bridge.NOTHING_SENT)

    @pytest.mark.parametrize("error", [TimeoutError(), OSError("pipe closed")])
    def test_no_answer_is_outcome_unknown_never_nothing_sent(self, pipe, error):
        """The plug-in may still be working: saying "nothing was sent" would be a lie."""
        pipe.error = error
        with pytest.raises(AutocadError) as caught:
            bridge.Bridge(1).run("j1", "loft", {})
        text = str(caught.value)
        assert text.startswith("Outcome unknown") and bridge.NOTHING_SENT not in text

    def test_not_connected(self, monkeypatch):
        monkeypatch.setattr(bridge.Bridge, "find", lambda self: None)
        with pytest.raises(bridge.BridgeRefused) as caught:
            bridge.Bridge(1).run("j1", "loft", {})
        assert str(caught.value) == bridge.NOT_CONNECTED


class TestPluginRunner:
    def test_none_outside_a_job(self, monkeypatch):
        monkeypatch.setattr(gate, "_current", None)
        assert gate.plugin_runner() is None

    def test_none_with_the_bridge_off(self, monkeypatch):
        monkeypatch.setattr(gate, "_current", gate.Job("t", Risk.CHANGE, "T", "a.dwg", None, None, False, 0.0))
        assert gate.plugin_runner() is None

    def test_inside_a_job_it_runs_in_that_job(self, monkeypatch):
        calls = []

        class FakeBridge:
            def run(self, job, operation, args):
                calls.append((job, operation, args))
                return {"ok": 1}

        monkeypatch.setattr(gate, "_current", gate.Job("t", Risk.CHANGE, "T", "a.dwg", FakeBridge(), "j9", False, 0.0))
        assert gate.plugin_runner()("shell", {"thickness": 3}) == {"ok": 1}
        assert calls == [("j9", "shell", {"thickness": 3})]


# ---------------------------------------------------------------------------
# The tools, against a fake plug-in
# ---------------------------------------------------------------------------


class Found:
    def __init__(self, handle, name="AcDb3dSolid"):
        self.Handle, self.ObjectName, self.Layer = handle, name, "0"
        self.Document = self

    def HandleToObject(self, handle):
        return Found(handle, self.ObjectName)


class Doc:
    def __init__(self, ucs=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))):
        self.ucs = ucs

    def GetVariable(self, name):
        return dict(zip(("UCSORG", "UCSXDIR", "UCSYDIR"), self.ucs, strict=True))[name]

    def HandleToObject(self, handle):
        return Found(handle)


class Plugin:
    """Stands in for the plug-in: records each operation, answers with ``reply``."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.reply: dict = {"handle": "2A", "volume_before": 6000.0, "volume_after": 5800.0}

    def __call__(self, operation, args):
        self.calls.append((operation, args))
        return self.reply


@pytest.fixture
def plugin(monkeypatch):
    fake = Plugin()
    doc = Doc()

    async def run(fn):
        return fn()

    for module in (solid_edits, superhatch):
        monkeypatch.setattr(module, "run", run)
        monkeypatch.setattr(module, "get_doc", lambda: doc)
        monkeypatch.setattr(module, "require_idle", lambda d: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: fake)
    fake.doc = doc
    return fake


def call(coro):
    answer = asyncio.run(coro)
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


def error(coro):
    answer = asyncio.run(coro)
    assert answer.startswith("Error"), answer
    return answer


class TestSolidEdits:
    def test_fillet_by_word(self, plugin):
        out = call(solid_edits.autocad_fillet_solid_edges(handle="2A", radius=5, edges="vertical"))
        assert plugin.calls == [("fillet_edges", {"handle": "2A", "radius": 5.0, "edges": "vertical"})]
        assert out["handle"] == "2A"

    def test_fillet_by_number(self, plugin):
        call(solid_edits.autocad_fillet_solid_edges(handle="2A", radius=5, edges=[0, 3]))
        assert plugin.calls[0][1]["edges"] == [0, 3]

    def test_chamfer_from_one_face_takes_a_word_or_a_number(self, plugin):
        call(solid_edits.autocad_chamfer_solid_edges(handle="2A", face="top", distance=3))
        call(solid_edits.autocad_chamfer_solid_edges(handle="2A", face=4, distance=3, other_distance=5, edges=[1, 2]))
        assert plugin.calls[0] == ("chamfer_edges", {"handle": "2A", "face": "top", "distance": 3.0})
        assert plugin.calls[1] == ("chamfer_edges", {"handle": "2A", "face": [4], "distance": 3.0, "other_distance": 5.0, "edges": [1, 2]})

    def test_shell_goes_inside_unless_asked(self, plugin):
        call(solid_edits.autocad_shell_solid(handle="2A", thickness=2, remove_faces="top"))
        call(solid_edits.autocad_shell_solid(handle="2A", thickness=2, outward=True))
        assert plugin.calls[0] == ("shell", {"handle": "2A", "thickness": 2.0, "outward": False, "remove": "top"})
        assert plugin.calls[1] == ("shell", {"handle": "2A", "thickness": 2.0, "outward": True})

    def test_press_pull_takes_the_taper_in_degrees(self, plugin):
        call(solid_edits.autocad_press_pull_faces(handle="2A", faces="top", distance=150, taper=10))
        operation, args = plugin.calls[0]
        assert operation == "press_pull" and args["faces"] == "top" and args["distance"] == 150.0
        assert args["taper"] == pytest.approx(math.radians(10))

    def test_press_pull_needs_a_distance(self, plugin):
        assert "zero" in error(solid_edits.autocad_press_pull_faces(handle="2A", faces="top", distance=0))
        assert plugin.calls == []

    def test_loft_sends_the_outlines_in_order(self, plugin):
        plugin.reply = {"created": True, "handle": "3F", "sections": 2, "volume": 1.0}
        out = call(solid_edits.autocad_loft(sections=["2A", "2B"], ruled=True, layer="M-DUCT", color="cyan"))
        assert plugin.calls == [("loft", {"sections": ["2A", "2B"], "ruled": True, "closed": False, "layer": "M-DUCT", "color": 4})]
        assert out["created"] is True and out["handle"] == "3F" and out["verified"] is True

    def test_loft_takes_guides_or_a_path_not_both(self, plugin):
        assert "not both" in error(solid_edits.autocad_loft(sections=["2A", "2B"], guides=["5"], path="6"))
        assert plugin.calls == []

    def test_thicken_makes_a_new_solid_and_keeps_the_surface(self, plugin):
        plugin.reply = {"created": True, "handle": "4C", "surface": "2A", "thickness": 3.0, "both_sides": False}
        out = call(solid_edits.autocad_thicken_surface(handle="2A", thickness=3))
        assert plugin.calls == [("thicken", {"handle": "2A", "thickness": 3.0, "both_sides": False})]
        assert out["handle"] == "4C" and out["surface"] == "2A"

    def test_the_listing_is_cut_to_the_limit_and_says_so(self, plugin):
        plugin.reply = {
            "handle": "2A",
            "faces": [{"index": i} for i in range(6)],
            "edges": [{"index": i} for i in range(12)],
        }
        out = call(solid_edits.autocad_list_solid_faces_and_edges(handle="2A", limit=5))
        assert plugin.calls == [("solid_topology", {"handle": "2A"})]
        assert out["face_count"] == 6 and out["edge_count"] == 12
        assert len(out["faces"]) == 5 and len(out["edges"]) == 5
        assert "5" in out["note"] and "top" in out["how_to_pick"]

    def test_a_change_counts_as_a_write_and_a_listing_does_not(self, plugin):
        before = connection.write_count()
        call(solid_edits.autocad_list_solid_faces_and_edges(handle="2A"))
        assert connection.write_count() == before
        call(solid_edits.autocad_fillet_solid_edges(handle="2A", radius=5, edges="all"))
        assert connection.write_count() == before + 1

    def test_without_the_plug_in_it_says_why(self, plugin, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        text = error(solid_edits.autocad_fillet_solid_edges(handle="2A", radius=5, edges="all"))
        assert "plug-in" in text and "--no-bridge" in text

    def test_autocads_refusal_reaches_the_chat(self, plugin, monkeypatch):
        def refuse(operation, args):
            raise AutocadError("AutoCAD would not shell it at 50 (InvalidInput). Nothing was changed.")

        monkeypatch.setattr(_shared, "plugin_runner", lambda: refuse)
        text = error(solid_edits.autocad_shell_solid(handle="2A", thickness=50))
        assert "would not shell" in text and "Nothing was changed" in text


class TestSuperHatch:
    def test_a_block_is_tiled_inside_the_outline(self, plugin):
        plugin.reply = {"created": True, "handle": "5D", "block": "SUPERHATCH-1", "tile": "PAVER", "tiles": 40}
        out = call(superhatch.autocad_super_hatch(boundary="2A", block="PAVER", layer="L-PAVING"))
        assert plugin.calls == [("super_hatch", {"boundary": "2A", "block": "PAVER", "scale": 1.0, "angle": 0.0, "layer": "L-PAVING"})]
        assert out["handle"] == "5D" and out["tiles"] == 40 and out["verified"] is True

    def test_spacing_origin_and_angle_are_passed_in_world_terms(self, plugin):
        call(superhatch.autocad_super_hatch(boundary="2A", block="PAVER", spacing=[600, 300], origin=[100, 50], angle=30, scale=2))
        args = plugin.calls[0][1]
        assert args["spacing"] == [600.0, 300.0] and args["origin"] == [100.0, 50.0] and args["scale"] == 2.0
        assert args["angle"] == pytest.approx(math.radians(30))

    def test_on_a_turned_ucs_the_grid_turns_with_it(self, plugin):
        plugin.doc.ucs = ((1000.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0))
        call(superhatch.autocad_super_hatch(boundary="2A", block="PAVER", origin=[0, 0], angle=0, coords="ucs"))
        args = plugin.calls[0][1]
        assert args["origin"] == pytest.approx([1000.0, 0.0])
        assert args["angle"] == pytest.approx(math.pi / 2)

    @pytest.mark.parametrize("layer", ["L-PAVING\nX", "L|PAVING", "L-PAV\tING", "   "])
    def test_a_bad_layer_name_is_refused_before_anything_is_sent(self, plugin, layer):
        # S13's follow-up to D-139: the layer was passed to the plug-in unchecked.
        assert "layer name" in error(superhatch.autocad_super_hatch(boundary="2A", block="PAVER", layer=layer))
        assert plugin.calls == []

    def test_the_layer_name_is_sent_trimmed(self, plugin):
        call(superhatch.autocad_super_hatch(boundary="2A", block="PAVER", layer="  L-PAVING "))
        assert plugin.calls[0][1]["layer"] == "L-PAVING"

    @pytest.mark.parametrize("spacing", [[600], [600, 0], [-1, 300]])
    def test_a_spacing_needs_two_sizes_above_zero(self, plugin, spacing):
        assert "spacing" in error(superhatch.autocad_super_hatch(boundary="2A", block="PAVER", spacing=spacing))
        assert plugin.calls == []


def test_levels():
    assert risk_of("autocad_list_solid_faces_and_edges") is Risk.READ
    for tool in (
        "autocad_loft",
        "autocad_fillet_solid_edges",
        "autocad_chamfer_solid_edges",
        "autocad_shell_solid",
        "autocad_press_pull_faces",
        "autocad_thicken_surface",
        "autocad_super_hatch",
    ):
        assert risk_of(tool) is Risk.CHANGE, tool


# ---------------------------------------------------------------------------
# Review fixes (2026-10-29)
# ---------------------------------------------------------------------------


def test_a_pipe_that_cannot_be_opened_means_nothing_was_sent(pipe):
    """Only a failure after the request went out is "outcome unknown"."""
    pipe.error = bridge.PipeUnavailable("the pipe is gone")
    with pytest.raises(bridge.BridgeRefused) as caught:
        bridge.Bridge(1).run("j1", "loft", {})
    assert str(caught.value).endswith(bridge.NOTHING_SENT)


class TestMadeButNotReadBack:
    """The plug-in made it; COM could not read it straight back (AutoCAD still busy).

    Reporting an error would make the chat try again and make it twice.
    """

    @pytest.fixture
    def busy(self, plugin):
        def refuse(handle):
            raise AutocadError("call was rejected by callee")

        plugin.doc.HandleToObject = refuse
        return plugin

    def test_a_loft(self, busy):
        busy.reply = {"created": True, "handle": "3F", "sections": 2}
        out = call(solid_edits.autocad_loft(sections=["2A", "2B"]))
        assert out["created"] is True and out["handle"] == "3F" and out["verified"] is False
        assert "do not make it again" in out["warning"]

    def test_a_super_hatch(self, busy):
        busy.reply = {"created": True, "handle": "5D", "block": "SUPERHATCH-1", "tiles": 40}
        out = call(superhatch.autocad_super_hatch(boundary="2A", block="PAVER"))
        assert out["handle"] == "5D" and out["tiles"] == 40 and out["verified"] is False
