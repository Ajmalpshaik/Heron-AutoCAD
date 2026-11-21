"""Layer states, isolate and merge (#107, D-81), no AutoCAD.

The rules are plain functions: what a layer state remembers, what isolating
changes, which objects a merge moves and when an old layer may go. The tools
are checked against fake COM objects and a fake plug-in.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import _shared, layer_states, layers
from autocad_mcp.tools.layer_states import (
    ISOLATE_MASK,
    ISOLATE_STATE,
    check_merge,
    current_from,
    escape_wildcards,
    isolate_description,
    isolate_plan,
    mask_of,
    merge_counts,
    merge_targets,
)


def row(name, on=True, frozen=False, locked=False):
    return {"name": name, "on": on, "frozen": frozen, "locked": locked}


class TestMask:
    def test_everything_unless_asked(self):
        assert mask_of(None) is None

    def test_the_bits_are_autocads(self):
        assert mask_of(["on", "frozen", "locked"]) == 7 == ISOLATE_MASK
        assert mask_of(["Color", "transparency"]) == 32 | 1024

    def test_a_word_it_does_not_know_names_the_ones_it_does(self):
        with pytest.raises(ValueError, match="lineweight"):
            mask_of(["visibility"])

    def test_an_empty_list_is_refused(self):
        with pytest.raises(ValueError, match="at least one"):
            mask_of([])


class TestIsolatePlan:
    LAYERS = [row("0"), row("M-DUCT"), row("M-PIPE"), row("A-WALL", on=False), row("E-LIGHT", frozen=True)]

    def changes(self, plan):
        return {(c["layer"], c["property"]): c["to"] for c in plan["changes"]}

    def test_every_other_layer_goes_off(self):
        plan = isolate_plan(self.LAYERS, ["m-duct"], "M-DUCT")
        assert self.changes(plan) == {("0", "on"): False, ("M-PIPE", "on"): False, ("E-LIGHT", "on"): False}
        assert plan["kept"] == ["M-DUCT"] and plan["make_current"] is None

    def test_a_layer_already_off_is_not_written_again(self):
        plan = isolate_plan(self.LAYERS, ["M-DUCT"], "M-DUCT")
        assert ("A-WALL", "on") not in self.changes(plan)

    def test_kept_layers_are_turned_on_and_thawed(self):
        plan = isolate_plan(self.LAYERS, ["A-WALL", "E-LIGHT"], "A-WALL")
        got = self.changes(plan)
        assert got[("A-WALL", "on")] is True and got[("E-LIGHT", "frozen")] is False

    def test_freeze_freezes_the_others(self):
        plan = isolate_plan(self.LAYERS, ["M-DUCT"], "M-DUCT", "freeze")
        assert self.changes(plan)[("M-PIPE", "frozen")] is True
        assert ("E-LIGHT", "frozen") not in self.changes(plan)

    def test_lock_locks_the_others_and_unlocks_the_kept(self):
        plan = isolate_plan([row("M-DUCT", locked=True), row("M-PIPE")], ["M-DUCT"], "M-PIPE", "lock")
        assert self.changes(plan) == {("M-DUCT", "locked"): False, ("M-PIPE", "locked"): True}
        assert plan["make_current"] is None  # a locked current layer is still current

    def test_a_current_layer_that_would_be_hidden_hands_over_first(self):
        plan = isolate_plan(self.LAYERS, ["M-PIPE", "M-DUCT"], "0", "freeze")
        assert plan["make_current"] == "M-PIPE"

    def test_a_layer_given_twice_is_kept_once(self):
        assert isolate_plan(self.LAYERS, ["M-DUCT", "m-duct"], "0")["kept"] == ["M-DUCT"]

    def test_an_unknown_layer_is_refused(self):
        with pytest.raises(ValueError, match="M-GAS"):
            isolate_plan(self.LAYERS, ["M-GAS"], "0")

    def test_the_current_layer_rides_in_the_saved_states_description(self):
        assert current_from(isolate_description("M-DUCT SUPPLY")) == "M-DUCT SUPPLY"
        assert current_from("someone else's state") is None


class TestMergeRules:
    LAYERS = ["0", "M-DUCT", "DUCT", "M-DUCT-OLD", "XREF|M-DUCT"]

    def test_names_come_back_as_the_drawing_has_them(self):
        assert check_merge(["duct", "m-duct-old"], "m-duct", self.LAYERS) == (["DUCT", "M-DUCT-OLD"], "M-DUCT")

    @pytest.mark.parametrize(
        ("sources", "into", "match"),
        [
            (["DUCT"], "M-GAS", "no layer called 'M-GAS'"),
            (["GAS"], "M-DUCT", "no layer called 'GAS'"),
            (["M-DUCT"], "m-duct", "into itself"),
            (["0"], "M-DUCT", "layer 0"),
            (["XREF|M-DUCT"], "M-DUCT", "xref"),
        ],
    )
    def test_refusals(self, sources, into, match):
        with pytest.raises(ValueError, match=match):
            check_merge(sources, into, self.LAYERS)

    def test_a_merge_moves_only_what_is_on_the_old_layers_each_once(self):
        items = [
            {"handle": "1A", "layer": "DUCT", "where": "drawing"},
            {"handle": "1B", "layer": "duct", "where": "blocks"},
            {"handle": "1C", "layer": "M-DUCT", "where": "drawing"},
            {"handle": "1D", "layer": "DUCT-2", "where": "drawing"},  # a filter wildcard would catch it
            {"handle": "1A", "layer": "DUCT", "where": "drawing"},
            {"handle": "1E", "layer": "M-DUCT-OLD", "where": "attributes"},
        ]
        moving = merge_targets(items, ["DUCT", "M-DUCT-OLD"])
        assert [m["handle"] for m in moving] == ["1A", "1B", "1E"]
        assert merge_counts(moving, ["DUCT", "M-DUCT-OLD"]) == {
            "DUCT": {"drawing": 1, "blocks": 1, "attributes": 0},
            "M-DUCT-OLD": {"drawing": 0, "blocks": 0, "attributes": 1},
        }

    def test_a_layer_name_is_read_literally_by_the_selection_filter(self):
        assert escape_wildcards("M-DUCT#1") == "M`-DUCT`#1"
        assert escape_wildcards("A.B@[x]~") == "A`.B`@`[x`]`~"
        assert escape_wildcards("PLAIN") == "PLAIN"


# ---------------------------------------------------------------------------
# Fake COM
# ---------------------------------------------------------------------------


class Layer:
    def __init__(self, name, on=True, frozen=False, locked=False, delete_ok=True, owner=None):
        self.Name, self.LayerOn, self.Freeze, self.Lock = name, on, frozen, locked
        self.deleted = False
        self.delete_ok = delete_ok
        self.owner = owner

    def Delete(self):  # noqa: N802 - COM name
        if not self.delete_ok:
            raise RuntimeError("layer is referenced")
        self.deleted = True
        self.owner.items.remove(self)


class Layers:
    def __init__(self, layers):
        self.items = list(layers)
        for layer in self.items:
            layer.owner = self

    @property
    def Count(self):  # noqa: N802 - COM name
        return len(self.items)

    def Item(self, key):  # noqa: N802 - COM name
        if isinstance(key, int):
            return self.items[key]
        for layer in self.items:
            if layer.Name.casefold() == str(key).casefold():
                return layer
        raise KeyError(key)


class Entity:
    def __init__(self, handle, layer, attributes=(), locked_out=False):
        self.Handle, self._layer, self._attributes, self.locked_out = handle, layer, list(attributes), locked_out
        self.HasAttributes = bool(attributes)

    @property
    def Layer(self):  # noqa: N802 - COM name
        return self._layer

    @Layer.setter
    def Layer(self, value):  # noqa: N802 - COM name
        if self.locked_out:
            raise RuntimeError("on a locked layer")
        self._layer = value

    def GetAttributes(self):  # noqa: N802 - COM name
        return tuple(self._attributes)


class Block:
    def __init__(self, name, entities=(), layout=False, xref=False):
        self.Name, self.items, self.IsLayout, self.IsXRef = name, list(entities), layout, xref
        self.Count = len(self.items)

    def Item(self, i):  # noqa: N802 - COM name
        return self.items[i]


class Blocks:
    def __init__(self, blocks):
        self.items = list(blocks)
        self.Count = len(self.items)

    def Item(self, i):  # noqa: N802 - COM name
        return self.items[i]


class Doc:
    def __init__(self, layers, spaces=(), blocks=()):
        self.Layers = Layers(layers)
        self.spaces = list(spaces)
        self.Blocks = Blocks(blocks)
        self.ActiveLayer = self.Layers.items[0]
        self.handles = {e.Handle: e for e in self.spaces}

    def HandleToObject(self, handle):  # noqa: N802 - COM name
        return self.handles[handle]

    def StartUndoMark(self):  # noqa: N802 - COM name
        pass

    def EndUndoMark(self):  # noqa: N802 - COM name
        pass


class FakePlugin:
    def __init__(self):
        self.calls: list = []
        self.states: dict[str, dict] = {}
        self.restore_changes: list = []

    def __call__(self, operation, args):
        self.calls.append((operation, dict(args)))
        if operation == "layer_state_names":
            return {"layer_states": [{"name": n, **v} for n, v in self.states.items()]}
        if operation == "layer_state":
            name = args["name"]
            if args["action"] == "save":
                if name in self.states and args.get("keep_existing"):
                    return {"action": "save", "name": name, "kept_existing": True}
                self.states[name] = {"description": args.get("description") or "", "remembers": ["on"]}
                return {"action": "save", "name": name, "replaced": False, "remembers": ["on"], "layers": 3}
            if args["action"] == "restore":
                state = self.states[name]
                if args.get("delete_after"):
                    del self.states[name]
                return {"action": "restore", "name": name, "description": state["description"],
                        "changes": self.restore_changes}
            if args["action"] == "delete":
                del self.states[name]
                return {"action": "delete", "name": name}
        raise AssertionError(operation)


@pytest.fixture
def cad(monkeypatch):
    fake = FakePlugin()
    holder: dict = {}

    async def run(fn):
        return fn()

    def select_filtered(doc, entity_type=None, layer=None, *rest, name=None, **kw):
        if entity_type == "block":
            return [e for e in doc.spaces if e.HasAttributes]
        # The filter reads the escaped name literally, as AutoCAD does.
        plain = layer.replace("`", "")
        return [e for e in doc.spaces if e.Layer.casefold() == plain.casefold()]

    for module in (layer_states, layers):
        monkeypatch.setattr(module, "run", run)
        monkeypatch.setattr(module, "get_doc", lambda: holder["doc"])
    monkeypatch.setattr(layer_states, "require_idle", lambda d: None)
    monkeypatch.setattr(layer_states, "select_filtered", select_filtered)
    monkeypatch.setattr(layer_states, "iter_selection", lambda sel: iter(sel))
    monkeypatch.setattr(layer_states, "discard_selection_set", lambda doc, name=None: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: fake)
    fake.holder = holder
    return fake


def call(coro):
    answer = asyncio.run(coro)
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


def error(coro):
    answer = asyncio.run(coro)
    assert answer.startswith("Error"), answer
    return answer


class TestLayerStatesTool:
    def test_save_sends_the_mask_and_description(self, cad):
        cad.holder["doc"] = Doc([Layer("0")])
        out = call(layer_states.autocad_layer_states(action="save", name="COORD", remembers=["on", "frozen"], description="for the MEP check"))
        assert cad.calls == [("layer_state", {"action": "save", "name": "COORD", "mask": 3, "description": "for the MEP check"})]
        assert out["before_after"] == [{"layer": "COORD", "property": "layer state", "from": "not there", "to": "saved"}]

    def test_save_without_remembers_lets_the_plug_in_save_everything(self, cad):
        cad.holder["doc"] = Doc([Layer("0")])
        call(layer_states.autocad_layer_states(action="save", name="ALL"))
        assert "mask" not in cad.calls[0][1]

    def test_restore_reports_each_layer_it_changed(self, cad):
        cad.holder["doc"] = Doc([Layer("0")])
        cad.states["ISSUE"] = {"description": "", "remembers": ["on"]}
        cad.restore_changes = [{"layer": "M-DUCT", "property": "on", "from": False, "to": True}]
        out = call(layer_states.autocad_layer_states(action="restore", name="ISSUE"))
        assert out["before_after"] == cad.restore_changes

    def test_heron_isolate_state_is_left_to_unisolate(self, cad):
        cad.holder["doc"] = Doc([Layer("0")])
        assert "unisolate" in error(layer_states.autocad_layer_states(action="restore", name="heron-isolate"))
        assert cad.calls == []

    def test_list_layers_carries_the_saved_states(self, cad):
        cad.holder["doc"] = Doc([Layer("0")])
        cad.states["ISSUE"] = {"description": "plot set", "remembers": ["on"]}
        out = call(layers.autocad_list_layers())
        assert out["layer_states"] == [{"name": "ISSUE", "description": "plot set", "remembers": ["on"]}]
        assert out["count"] == 1 and out["layers"][0]["name"] == "0"  # the layer list itself is unchanged

    def test_without_the_plug_in_list_layers_still_lists_layers(self, cad, monkeypatch):
        cad.holder["doc"] = Doc([Layer("0")])
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        out = call(layers.autocad_list_layers())
        assert out["count"] == 1 and out["layer_states"] is None and "plug-in" in out["layer_states_note"]


class TestIsolateTool:
    def doc(self):
        duct = Entity("2A", "M-DUCT")
        return Doc([Layer("0"), Layer("M-DUCT"), Layer("M-PIPE"), Layer("A-WALL", on=False)], spaces=[duct])

    def test_it_saves_the_state_first_then_hides_the_rest(self, cad):
        cad.holder["doc"] = doc = self.doc()
        out = call(layer_states.autocad_isolate_layers(handles=["2A"]))
        operation, args = cad.calls[0]
        assert operation == "layer_state" and args["action"] == "save" and args["name"] == ISOLATE_STATE
        assert args["mask"] == ISOLATE_MASK and args["keep_existing"] is True and "current layer was 0" in args["description"]
        assert [la.Name for la in doc.Layers.items if not la.LayerOn] == ["0", "M-PIPE", "A-WALL"]
        assert doc.ActiveLayer.Name == "M-DUCT" and out["current_layer"] == "M-DUCT"
        assert {"variable": "CLAYER", "property": "current layer", "from": "0", "to": "M-DUCT"} in out["before_after"]

    def test_isolating_twice_keeps_the_first_state(self, cad):
        cad.holder["doc"] = self.doc()
        call(layer_states.autocad_isolate_layers(layers=["M-DUCT"]))
        out = call(layer_states.autocad_isolate_layers(layers=["M-PIPE"]))
        assert out["already_isolated"] is True and "first isolate" in out["note"]
        assert "current layer was 0" in cad.states[ISOLATE_STATE]["description"]

    def test_unisolate_restores_deletes_and_puts_the_current_layer_back(self, cad):
        cad.holder["doc"] = doc = self.doc()
        call(layer_states.autocad_isolate_layers(handles=["2A"]))
        for layer in doc.Layers.items:  # what the plug-in's restore would do
            layer.LayerOn = layer.Name != "A-WALL"
        cad.restore_changes = [{"layer": "0", "property": "on", "from": False, "to": True}]
        out = call(layer_states.autocad_isolate_layers(action="unisolate"))
        assert ("layer_state", {"action": "restore", "name": ISOLATE_STATE, "delete_after": True}) in cad.calls
        assert ISOLATE_STATE not in cad.states
        assert doc.ActiveLayer.Name == "0" and out["current_layer"] == "0"

    def test_unisolate_with_nothing_isolated_changes_nothing(self, cad):
        cad.holder["doc"] = self.doc()
        text = error(layer_states.autocad_isolate_layers(action="unisolate"))
        assert "Nothing is isolated" in text and "LAYUNISO" in text
        assert [c[0] for c in cad.calls] == ["layer_state_names"]

    def test_isolate_needs_something_to_keep(self, cad):
        cad.holder["doc"] = self.doc()
        assert "Say what to keep" in error(layer_states.autocad_isolate_layers())

    def test_an_unknown_layer_changes_nothing(self, cad):
        cad.holder["doc"] = doc = self.doc()
        assert "M-GAS" in error(layer_states.autocad_isolate_layers(layers=["M-GAS"]))
        assert cad.calls == [] and all(la.LayerOn for la in doc.Layers.items if la.Name != "A-WALL")


class TestMergeTool:
    def doc(self, delete_ok=True, locked_out=False):
        attr = Entity("3B", "DUCT")
        tag = Entity("3A", "M-DUCT", attributes=[attr])
        inside = Entity("4A", "DUCT")
        return Doc(
            [Layer("0"), Layer("M-DUCT"), Layer("DUCT", locked=True, delete_ok=delete_ok), Layer("DUCT-2")],
            spaces=[Entity("2A", "DUCT", locked_out=locked_out), Entity("2B", "DUCT-2"), tag],
            blocks=[Block("*Model_Space", layout=True), Block("VALVE", [inside, Entity("4B", "0")]),
                    Block("XR", [Entity("5A", "DUCT")], xref=True)],
        )

    def test_without_confirm_it_says_what_would_move_and_changes_nothing(self, cad):
        cad.holder["doc"] = doc = self.doc()
        out = call(layer_states.autocad_merge_layers(layers=["duct"], into="M-DUCT"))
        assert out["confirmed"] is False and out["would_move"] == 3
        assert out["counts"] == {"DUCT": {"drawing": 1, "blocks": 1, "attributes": 1}}
        assert doc.handles["2A"].Layer == "DUCT" and "DUCT" in [la.Name for la in doc.Layers.items]

    def test_it_moves_everywhere_but_xrefs_then_removes_the_empty_layer(self, cad):
        cad.holder["doc"] = doc = self.doc()
        doc.ActiveLayer = doc.Layers.Item("DUCT")
        out = call(layer_states.autocad_merge_layers(layers=["DUCT"], into="m-duct", confirm=True))
        assert out["moved"] == 3 and out["removed"] == ["DUCT"] and out["kept"] == []
        assert doc.handles["2A"].Layer == "M-DUCT" and doc.handles["2B"].Layer == "DUCT-2"
        assert doc.Blocks.items[1].items[0].Layer == "M-DUCT" and doc.Blocks.items[2].items[0].Layer == "DUCT"
        assert doc.handles["3A"].GetAttributes()[0].Layer == "M-DUCT"
        assert doc.ActiveLayer.Name == "M-DUCT"
        assert {"layer": "DUCT", "property": "layer", "from": "there", "to": "merged and removed"} in out["before_after"]

    def test_a_layer_with_an_object_left_on_it_is_kept_and_relocked(self, cad):
        cad.holder["doc"] = doc = self.doc(locked_out=True)
        out = call(layer_states.autocad_merge_layers(layers=["DUCT"], into="M-DUCT", confirm=True))
        assert out["removed"] == [] and out["kept"][0]["layer"] == "DUCT" and "1 object" in out["kept"][0]["why"]
        assert out["failed"][0]["handle"] == "2A"
        assert doc.Layers.Item("DUCT").Lock is True

    def test_a_layer_autocad_will_not_remove_is_kept_with_the_reason(self, cad):
        cad.holder["doc"] = self.doc(delete_ok=False)
        out = call(layer_states.autocad_merge_layers(layers=["DUCT"], into="M-DUCT", confirm=True))
        assert out["moved"] == 3 and out["removed"] == [] and "would not remove" in out["kept"][0]["why"]

    def test_layer_zero_is_refused_before_anything_is_read(self, cad):
        cad.holder["doc"] = doc = self.doc()
        assert "layer 0" in error(layer_states.autocad_merge_layers(layers=["0"], into="M-DUCT", confirm=True))
        assert doc.handles["2A"].Layer == "DUCT"


def test_levels():
    for tool in ("autocad_layer_states", "autocad_isolate_layers", "autocad_merge_layers"):
        assert risk_of(tool) is Risk.CHANGE, tool
    assert risk_of("autocad_list_layers") is Risk.READ
