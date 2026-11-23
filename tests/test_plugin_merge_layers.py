"""autocad_merge_layers in the plug-in: one read, one transaction (#199, D-146), no AutoCAD.

Over COM the merge reads every item of every block definition (2-3 round trips
each), then writes one call per moved object; a failure half way leaves part of
it moved. The plug-in reads the old layers' objects in one go (layer_objects)
and makes the whole merge in one transaction (merge_layers): every planned
object moves and the empty old layers go, or nothing changes. The answer must
be the same either way, so each merge runs twice over one fake drawing, once
through a fake plug-in and once over fake COM; the answers are compared as text
and the drawings left behind compared too.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from autocad_mcp.core import bridge
from autocad_mcp.core.bridge import NEWER_READS, OLD_PLUGIN, READS_SINCE, BridgeRefused
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import _shared, layer_states

ROOT = Path(__file__).resolve().parents[1]
READ, CHANGE = "layer_objects", "merge_layers"


# ---- the fake drawing: one spec, read over COM or by the plug-in ------------------------

class Layer:
    def __init__(self, name, locked=False, referenced=False):
        self.Name, self.Lock, self.referenced = name, locked, referenced
        self.Freeze = False
        self.gone = False


class Layers:
    def __init__(self, doc, layers):
        self.doc, self.items = doc, layers

    @property
    def Count(self):  # noqa: N802 - COM's name
        return len(self.live())

    def live(self):
        return [la for la in self.items if not la.gone]

    def Item(self, key):  # noqa: N802 - COM's name
        if isinstance(key, int):
            return Removable(self.doc, self.live()[key])
        for layer in self.live():
            if layer.Name.casefold() == str(key).casefold():
                return Removable(self.doc, layer)
        raise RuntimeError("Key not found")


class Removable:
    """A COM layer: Name, Lock (writable), Freeze, Delete()."""

    def __init__(self, doc, layer):
        object.__setattr__(self, "_doc", doc)
        object.__setattr__(self, "_layer", layer)

    def __getattr__(self, name):
        return getattr(self._layer, name)

    def __setattr__(self, name, value):
        setattr(self._layer, name, value)

    def Delete(self):  # noqa: N802 - COM's name
        on_it = [o for o in self._doc.all_objects() if o.layer.casefold() == self._layer.Name.casefold()]
        if self._layer.referenced or on_it or self._doc.current.casefold() == self._layer.Name.casefold():
            raise RuntimeError("Object is referenced")
        self._layer.gone = True


class Obj:
    """A drawing object: in a space, a block definition, or an attribute on a block reference."""

    def __init__(self, handle, layer, attributes=(), stuck=False, defines=None):
        self.handle, self.layer, self.stuck = handle, layer, stuck
        self.attributes = list(attributes)
        self.defines = bool(attributes) if defines is None else defines


class Com:
    """A COM object over one Obj; every read counted."""

    def __init__(self, doc, obj):
        object.__setattr__(self, "_doc", doc)
        object.__setattr__(self, "_obj", obj)

    @property
    def Handle(self):  # noqa: N802 - COM's name
        self._doc.reads += 1
        return self._obj.handle

    @property
    def Layer(self):  # noqa: N802 - COM's name
        self._doc.reads += 1
        return self._obj.layer

    @Layer.setter
    def Layer(self, value):  # noqa: N802 - COM's name
        self._doc.writes += 1
        if self._obj.stuck:
            raise RuntimeError("eOnLockedLayer")
        self._obj.layer = value

    def __setattr__(self, name, value):
        if name == "Layer":
            Com.Layer.fset(self, value)
        else:
            raise AttributeError(name)

    @property
    def HasAttributes(self):  # noqa: N802 - COM's name
        return bool(self._obj.attributes)

    def GetAttributes(self):  # noqa: N802 - COM's name
        return tuple(Com(self._doc, a) for a in self._obj.attributes)


class Block:
    def __init__(self, name, items=(), layout=False, xref=False):
        self.Name, self.IsLayout, self.IsXRef = name, layout, xref
        self.objs = list(items)


class ComBlock:
    def __init__(self, doc, block):
        self.doc, self.block = doc, block
        self.Name, self.IsLayout, self.IsXRef = block.Name, block.IsLayout, block.IsXRef
        self.Count = len(block.objs)

    def Item(self, j):  # noqa: N802 - COM's name
        return Com(self.doc, self.block.objs[j])


class Blocks:
    def __init__(self, doc, blocks):
        self.doc, self.blocks = doc, blocks
        self.Count = len(blocks)

    def Item(self, i):  # noqa: N802 - COM's name
        return ComBlock(self.doc, self.blocks[i])


class Doc:
    def __init__(self, spec):
        layers, spaces, blocks, current = spec
        self.FullName = r"C:\a.dwg"
        self.Layers = Layers(self, layers)
        self.spaces = spaces
        self.blocks = blocks
        self.Blocks = Blocks(self, blocks)
        self.current = current
        self.reads = self.writes = self.selections = self.undo_marks = 0

    def all_objects(self):
        for obj in self.spaces:
            yield obj
            yield from obj.attributes
        for block in self.blocks:
            if not block.IsXRef:
                yield from block.objs

    @property
    def ActiveLayer(self):  # noqa: N802 - COM's name
        return self.Layers.Item(self.current)

    @ActiveLayer.setter
    def ActiveLayer(self, layer):  # noqa: N802 - COM's name
        self.current = layer.Name

    def HandleToObject(self, handle):  # noqa: N802 - COM's name
        for obj in self.all_objects():
            if obj.handle == handle:
                return Com(self, obj)
        raise RuntimeError("no such handle")

    def GetVariable(self, name):  # noqa: N802 - COM's name
        return 0

    def StartUndoMark(self):  # noqa: N802 - COM's name
        self.undo_marks += 1

    def EndUndoMark(self):  # noqa: N802 - COM's name
        pass

    def state(self):
        """What the drawing holds now: each layer (lock), each object's layer, the current layer."""
        return (
            [(la.Name, la.Lock) for la in self.Layers.live()],
            [(o.handle, o.layer) for o in self.all_objects()],
            [(o.handle, o.layer) for b in self.blocks if b.IsXRef for o in b.objs],
            self.current,
        )


def drawing(locked=True, referenced=False, stuck=False, current="DUCT", defines=True):
    layers = [Layer("0"), Layer("M-DUCT"), Layer("DUCT", locked=locked, referenced=referenced), Layer("Duct-Old"),
              Layer("M-PIPE")]
    tag = Obj("3A", "M-DUCT", attributes=[Obj("3B", "DUCT"), Obj("3C", "M-DUCT"), Obj("3D", "duct-old")],
              defines=defines)
    spaces = [Obj("2A", "DUCT", stuck=stuck), Obj("2B", "M-PIPE"), tag, Obj("2C", "Duct-Old"), Obj("2D", "DUCT"),
              Obj("3E", "M-PIPE", attributes=[Obj("3F", "M-PIPE")])]
    blocks = [Block("*Model_Space", layout=True), Block("*Paper_Space", layout=True),
              Block("VALVE", [Obj("4A", "DUCT"), Obj("4B", "0"), Obj("4C", "DUCT-OLD")]),
              Block("XR", [Obj("5A", "DUCT")], xref=True), Block("EMPTY")]
    return layers, spaces, blocks, current


# ---- the fake plug-in: the two operations as LayerMerging.cs does them ------------------

class FakePlugin:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.fail: dict[str, Exception] = {}
        self.report = None  # replaces merge_layers' answer when set
        self.make = drawing
        self.reset()

    def reset(self, **options):
        self.options = options
        self.doc = Doc(self.make(**options))

    def __call__(self, operation, args):
        self.calls.append((operation, json.loads(json.dumps(args))))  # what goes over the pipe
        if operation in self.fail:
            raise self.fail[operation]
        if operation == READ:
            return json.loads(json.dumps(self.read(args)))
        if operation == CHANGE:
            return json.loads(json.dumps(self.merge(args)))
        raise BridgeRefused(f"Heron in AutoCAD does not have the operation '{operation}'. Nothing was sent to AutoCAD.")

    def read(self, args):
        doc = self.doc
        old = {name.casefold() for name in args["layers"]}
        items = []
        for pairs in args["filters"]:
            assert [p[0] for p in pairs] == [8]
            wanted = pairs[0][1].replace("`", "").casefold()
            items += [[o.handle, o.layer, "drawing"] for o in doc.spaces if o.layer.casefold() == wanted]
        for block in doc.blocks:
            if block.IsLayout or block.IsXRef:
                continue
            items += [[o.handle, o.layer, "blocks"] for o in block.objs if o.layer.casefold() in old]
        assert args["inserts"] == [[0, "INSERT"]]
        unsure = False
        for ref in doc.spaces:
            found = [[a.handle, a.layer, "attributes"] for a in ref.attributes if a.layer.casefold() in old]
            items += found
            unsure = unsure or (bool(found) and not ref.defines)
        return {"items": items, "unsure": unsure}

    def merge(self, args):
        doc = self.doc
        before = doc.state()
        layers = {la.Name: la for la in doc.Layers.live()}
        into = args["into"]
        report = {"moved": len(args["handles"]), "current": None, "removed": [], "kept": []}
        if doc.current.casefold() in {s.casefold() for s in args["layers"]}:
            report["current"] = doc.current
            doc.current = into
        relock = set()
        for name in args["layers"]:
            if layers[name].Lock:
                layers[name].Lock = False
                relock.add(name)
        by_handle = {o.handle: o for o in doc.all_objects()}
        for handle in args["handles"]:
            if by_handle[handle].stuck:
                # The transaction is aborted: the drawing is as it was.
                doc.__init__(self.make(**self.options))
                assert doc.state() == before
                raise AutocadError(f"Object {handle} would not move to {into} (eOnLockedLayer), so nothing was "
                                   "merged: no object moved and no layer was removed. Nothing was changed.")
            by_handle[handle].layer = into
        for name in args["layers"]:
            used = layers[name].referenced or any(o.layer == name for o in doc.all_objects())
            if used:
                report["kept"].append([name, "it is still referenced"])
                if name in relock:
                    layers[name].Lock = True
            else:
                layers[name].gone = True
                report["removed"].append(name)
        return report if self.report is None else self.report(report)


@pytest.fixture
def cad(monkeypatch):
    plugin = FakePlugin()

    async def run(fn):
        return fn()

    def select_filtered(doc_, entity_type=None, layer=None, *rest, name=None, **kw):
        doc_.selections += 1
        if entity_type == "block":
            return [Com(doc_, o) for o in doc_.spaces]
        plain = layer.replace("`", "")
        return [Com(doc_, o) for o in doc_.spaces if o.layer.casefold() == plain.casefold()]

    monkeypatch.setattr(layer_states, "run", run)
    monkeypatch.setattr(layer_states, "get_doc", lambda: plugin.doc)
    monkeypatch.setattr(layer_states, "require_idle", lambda d: None)
    monkeypatch.setattr(layer_states, "select_filtered", select_filtered)
    monkeypatch.setattr(layer_states, "iter_selection", lambda sel: iter(sel))
    monkeypatch.setattr(layer_states, "discard_selection_set", lambda doc, name=None: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: plugin)
    monkeypatch.setattr(_shared, "plugin_version", lambda: READS_SINCE)
    plugin.use = lambda on: monkeypatch.setattr(_shared, "plugin_runner", (lambda: plugin) if on else (lambda: None))
    return plugin


def answer(coro) -> str:
    text = asyncio.run(coro)
    assert not text.startswith("Error"), text
    return text


def merge(**options):
    return layer_states.autocad_merge_layers(**{"layers": ["duct", "DUCT-OLD"], "into": "m-duct", **options})


def both(cad, make, **drawn):
    """The merge through the plug-in, then over COM, each on a fresh drawing: (answer, drawing left) each."""
    cad.reset(**drawn)
    cad.use(True)
    by_plugin = answer(make())
    assert cad.calls, "the plug-in was not asked"
    assert cad.doc.selections == 0 and cad.doc.writes == 0, "the plug-in path used COM as well"
    plugin_left, asked = cad.doc.state(), len(cad.calls)
    cad.reset(**drawn)
    cad.use(False)
    by_com = answer(make())
    assert len(cad.calls) == asked and cad.doc.selections > 0
    return (by_plugin, plugin_left), (by_com, cad.doc.state())


# ---- the same either way ----------------------------------------------------------------

DRAWINGS = [{}, {"locked": False}, {"current": "0"}, {"current": "Duct-Old"}]


class TestTheSameEitherWay:
    @pytest.mark.parametrize("drawn", DRAWINGS, ids=["locked-current", "unlocked", "other-current", "second-current"])
    @pytest.mark.parametrize("confirm", [False, True], ids=["preview", "confirmed"])
    def test_merge(self, cad, drawn, confirm):
        by_plugin, by_com = both(cad, lambda: merge(confirm=confirm), **drawn)
        assert by_plugin == by_com

    def test_one_layer(self, cad):
        by_plugin, by_com = both(cad, lambda: layer_states.autocad_merge_layers(layers=["Duct-Old"], into="M-PIPE",
                                                                                   confirm=True))
        assert by_plugin == by_com

    def test_what_it_moves_and_removes_is_what_com_does(self, cad):
        out = json.loads(answer(merge(confirm=True)))
        assert out["moved"] == 7 and out["removed"] == ["DUCT", "Duct-Old"] and out["kept"] == []
        assert out["counts"] == {"DUCT": {"drawing": 2, "blocks": 1, "attributes": 1},
                                 "Duct-Old": {"drawing": 1, "blocks": 1, "attributes": 1}}
        assert out["before_after"][0] == {"variable": "CLAYER", "property": "current layer", "from": "DUCT",
                                          "to": "M-DUCT"}
        layers, objects, xref, current = cad.doc.state()
        assert [name for name, _ in layers] == ["0", "M-DUCT", "M-PIPE"] and current == "M-DUCT"
        assert dict(objects)["4C"] == "M-DUCT" and xref == [("5A", "DUCT")]  # an xref's own objects stay

    def test_a_layer_still_used_is_kept_and_locked_again_the_reason_is_autocad_s_own(self, cad):
        (plugin_text, plugin_left), (com_text, com_left) = both(cad, lambda: merge(confirm=True), referenced=True)
        assert plugin_left == com_left
        plugin_out, com_out = json.loads(plugin_text), json.loads(com_text)
        # Only AutoCAD's own words in the brackets differ: COM's error, or the plug-in's purge.
        strip = re.compile(r"\(([^)]*)\)")
        assert strip.sub("()", plugin_text) == strip.sub("()", com_text)
        assert plugin_out["kept"] == [{"layer": "DUCT", "why": "AutoCAD would not remove it (it is still "
                                       "referenced); it is still used somewhere, for example by a viewport or a "
                                       "layer filter"}]
        assert "Object is referenced" in com_out["kept"][0]["why"]
        assert ("DUCT", True) in plugin_left[0]


class TestAllOrNone:
    def test_an_object_that_will_not_move_changes_nothing_through_the_plugin(self, cad):
        cad.reset(stuck=True)
        before = cad.doc.state()
        text = asyncio.run(merge(confirm=True))
        assert text.startswith("Error") and "Object 2A would not move" in text and "Nothing was changed" in text
        assert cad.doc.state() == before and cad.doc.writes == 0 and cad.doc.selections == 0

    def test_over_com_the_same_object_is_listed_and_its_layer_kept(self, cad):
        cad.reset(stuck=True)
        cad.use(False)
        out = json.loads(answer(merge(confirm=True)))
        assert out["failed"][0]["handle"] == "2A" and out["kept"][0]["layer"] == "DUCT"

    def test_the_merge_is_one_undo_step_either_way(self, cad):
        for on in (True, False):
            cad.reset()
            cad.use(on)
            answer(merge(confirm=True))
            assert cad.doc.undo_marks == 1

    def test_a_preview_changes_nothing_and_asks_only_the_read(self, cad):
        cad.reset()
        before = cad.doc.state()
        answer(merge())
        assert [c[0] for c in cad.calls] == [READ] and cad.doc.state() == before and cad.doc.undo_marks == 0


class TestWhatIsSent:
    def test_the_read_and_the_merge(self, cad):
        answer(merge(confirm=True))
        assert cad.calls[0] == (READ, {"layers": ["DUCT", "Duct-Old"], "filters": [[[8, "DUCT"]], [[8, "Duct`-Old"]]],
                                       "inserts": [[0, "INSERT"]]})
        assert cad.calls[1] == (CHANGE, {"layers": ["DUCT", "Duct-Old"], "into": "M-DUCT",
                                         "handles": ["2A", "2D", "2C", "4A", "4C", "3B", "3D"]})

    def test_a_name_with_wildcards_is_selected_literally(self, cad):
        cad.make = lambda **kw: ([Layer("0"), Layer("M-DUCT"), Layer("A#1")], [Obj("2A", "A#1")], [], "0")
        cad.reset()
        answer(layer_states.autocad_merge_layers(layers=["A#1"], into="M-DUCT"))
        assert cad.calls[0][1]["filters"] == [[[8, "A`#1"]]]


class TestFallsBackToCom:
    @pytest.mark.parametrize("refusal", [
        BridgeRefused(OLD_PLUGIN),
        BridgeRefused("Heron in AutoCAD does not have the operation 'layer_objects'. Update Heron so both sides "
                      "match. Nothing was sent to AutoCAD."),
        AutocadError("AutoCAD refused it (eInvalidInput). Nothing was changed."),
    ])
    def test_a_plugin_that_cannot_read_it_reads_over_com_and_still_merges_in_one_go(self, cad, refusal):
        cad.fail = {READ: refusal}
        cad.reset()
        by_plugin_write = answer(merge(confirm=True))
        assert [c[0] for c in cad.calls] == [READ, CHANGE] and cad.doc.selections > 0 and cad.doc.writes == 0
        left = cad.doc.state()
        cad.fail = {}
        (by_plugin, plugin_left), _ = both(cad, lambda: merge(confirm=True))
        assert (by_plugin_write, left) == (by_plugin, plugin_left)

    def test_a_plugin_without_the_merge_writes_over_com_by_handle(self, cad):
        cad.fail = {CHANGE: BridgeRefused("Heron in AutoCAD does not have the operation 'merge_layers'. Update Heron "
                                          "so both sides match. Nothing was sent to AutoCAD.")}
        cad.reset()
        text = answer(merge(confirm=True))
        assert cad.doc.selections == 0 and cad.doc.writes == 7  # read by the plug-in, each object moved over COM
        left = cad.doc.state()
        cad.fail = {}
        _, (by_com, com_left) = both(cad, lambda: merge(confirm=True))
        assert (text, left) == (by_com, com_left)

    def test_an_older_plugin_is_not_asked(self, cad, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_version", lambda: "1.7.0")
        cad.reset()
        answer(merge(confirm=True))
        assert cad.calls == [] and cad.doc.selections > 0

    @pytest.mark.parametrize("bad", [
        lambda found: {"items": found["items"]},
        lambda found: {**found, "unsure": "no"},
        lambda found: {**found, "items": [r[:2] for r in found["items"]]},
        lambda found: {**found, "items": [[r[0], r[1], "model"] for r in found["items"]]},
        lambda found: {**found, "items": [[r[0], None, r[2]] for r in found["items"]]},
    ], ids=["no-unsure", "unsure-text", "short", "where", "layer"])
    def test_a_read_this_server_cannot_read_as_com_is_read_over_com(self, cad, monkeypatch, bad):
        real = cad.read
        monkeypatch.setattr(cad, "read", lambda args: bad(real(args)))
        cad.reset()
        answer(merge())
        assert cad.doc.selections > 0

    def test_an_attribute_whose_definition_defines_none_is_read_over_com(self, cad):
        cad.reset(defines=False)
        answer(merge())
        assert cad.calls[0][0] == READ and cad.doc.selections > 0

    @pytest.mark.parametrize("refusal", [
        AutocadError(bridge.RUN_UNKNOWN.format(seconds=300, details="no answer")),
        BridgeRefused("The modeller pressed Stop in AutoCAD (HERONSTOP). Nothing was sent to AutoCAD."),
    ])
    def test_a_stop_or_no_answer_to_the_merge_is_said_never_merged_again_over_com(self, cad, refusal):
        cad.fail = {CHANGE: refusal}
        cad.reset()
        before = cad.doc.state()
        assert asyncio.run(merge(confirm=True)).startswith("Error")
        assert cad.doc.writes == 0 and cad.doc.state() == before

    def test_an_answer_to_the_merge_that_cannot_be_read_is_outcome_unknown(self, cad):
        cad.report = lambda report: {**report, "removed": ["DUCT"], "kept": []}  # a layer missing from both
        cad.reset()
        text = asyncio.run(merge(confirm=True))
        assert text.startswith("Error") and "Outcome unknown" in text and cad.doc.writes == 0


class TestThroughTheRealGate:
    """The merge inside its Change job: the answer line, Keep or Discard and the undo mark, the same either way."""

    @pytest.fixture
    def gated(self, cad, monkeypatch):
        import test_gate

        test_gate.env.__wrapped__(monkeypatch)  # the gate with the bridge and COM faked
        test_gate.FakeBridge.ask_to_keep = True

        def run(self, job, operation, args, timeout=None):
            return cad(operation, args)

        monkeypatch.setattr(test_gate.FakeBridge, "run", run, raising=False)
        monkeypatch.setattr(_shared, "plugin_runner", __import__("autocad_mcp.core.gate", fromlist=["gate"]).plugin_runner)
        monkeypatch.setattr(_shared, "plugin_version", lambda: None)  # not known: the plug-in is asked
        cad.bridge = test_gate.FakeBridge
        return cad

    def test_keep_or_discard_asks_about_the_same_merge_either_way(self, gated):
        # What the plug-in counts for the job from AutoCAD's own events: 7 objects and a layer table changed.
        gated.bridge.counted = {"added": 0, "modified": 8, "erased": 2}
        found = {}
        for through in (True, False):
            gated.reset()
            gated.bridge.calls = []
            gated.fail = {} if through else {
                READ: BridgeRefused("Heron in AutoCAD does not have the operation 'layer_objects'. Nothing was sent "
                                    "to AutoCAD."),
                CHANGE: BridgeRefused("Heron in AutoCAD does not have the operation 'merge_layers'. Nothing was "
                                      "sent to AutoCAD."),
            }
            text = asyncio.run(merge(confirm=True))
            assert (gated.doc.writes == 0) == through
            found[through] = (text, [c[:3] for c in gated.bridge.calls], gated.doc.state(), gated.doc.undo_marks)
        assert found[True] == found[False]
        text, calls, _, marks = found[True]
        assert text.splitlines()[0].startswith("DONE - ") and marks == 1
        assert calls[0][:3] == ("begin", "autocad_merge_layers", "change") and calls[-1][0] == "end"
        assert any(c[0] == "ask_keep" for c in calls)

    def test_a_refused_merge_is_said_and_asks_nothing_to_keep(self, gated):
        gated.reset(stuck=True)
        gated.bridge.counted = {"added": 0, "modified": 0, "erased": 0}
        text = asyncio.run(merge(confirm=True))
        assert "would not move" in text and "Nothing was changed" in text
        assert not any(c[0] == "ask_keep" for c in gated.bridge.calls)


class TestBothSidesKnowTheOperations:
    def test_the_plugin_lists_and_dispatches_them(self):
        listed = (ROOT / "autocad" / "Heron.AutoCAD.Bridge" / "PluginOperations.cs").read_text(encoding="utf-8")
        runner = (ROOT / "autocad" / "Heron.AutoCAD.Addin" / "PluginRunner.cs").read_text(encoding="utf-8")
        assert f'["{READ}"] = Risk.Read' in listed and f'["{CHANGE}"] = Risk.Change' in listed
        assert f'case "{READ}":' in runner and f'case "{CHANGE}":' in runner

    def test_the_read_is_named_newer(self):
        source = (ROOT / "src" / "autocad_mcp" / "tools" / "layer_states.py").read_text(encoding="utf-8")
        assert READ in set(re.findall(r'faster_read\("(\w+)"', source))
        assert CHANGE in set(re.findall(r'faster_change\("(\w+)"', source))
        assert READ in NEWER_READS
