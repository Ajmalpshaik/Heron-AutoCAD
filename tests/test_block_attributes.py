"""Block attributes (D-82, issue #115): definitions in make_block, and ATTSYNC.

Checked without AutoCAD: the attribute flags and the rules ATTDEF applies,
which inserts ATTSYNC touches, what each keeps, gains and loses, and what the
tools send to AutoCAD and to the plug-in.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.acad.block_attributes import (
    MODE_CONSTANT,
    MODE_INVISIBLE,
    MODE_PRESET,
    STACK_GAP,
    AttributeSpecError,
    clean_tag,
    flags_of,
    mode_of,
    plan_definitions,
    plan_sync,
    sync_one,
)
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import blocks

# ---------------------------------------------------------------------------
# Attribute definitions
# ---------------------------------------------------------------------------


class TestFlags:
    def test_the_mode_numbers_are_autocads(self):
        assert (MODE_INVISIBLE, MODE_CONSTANT, MODE_PRESET) == (1, 2, 8)

    @pytest.mark.parametrize(
        ("flags", "mode"),
        [({}, 0), ({"invisible": True}, 1), ({"constant": True}, 2), ({"preset": True}, 8), ({"invisible": True, "preset": True}, 9)],
    )
    def test_flags_make_the_mode_and_back(self, flags, mode):
        assert mode_of(**flags) == mode
        assert {k for k, v in flags_of(mode).items() if v} == set(flags)

    def test_each_attribute_carries_its_flags(self):
        (tag, size, make) = plan_definitions(
            [
                {"tag": "TAG", "default": "V-101"},
                {"tag": "SIZE", "default": "DN50", "invisible": True},
                {"tag": "MAKE", "default": "ACME", "constant": True},
            ],
            [0, 0],
            25.0,
        )
        assert (tag["mode"], size["mode"], make["mode"]) == (0, MODE_INVISIBLE, MODE_CONSTANT)
        assert size["invisible"] and not size["constant"] and make["constant"]

    def test_a_flag_must_be_true_or_false(self):
        with pytest.raises(AttributeSpecError, match="true or false"):
            plan_definitions([{"tag": "TAG", "invisible": "yes"}], [0, 0], 2.5)


class TestTags:
    def test_a_tag_is_stored_in_capitals(self):
        assert clean_tag(" valve_tag ") == "VALVE_TAG"

    @pytest.mark.parametrize("tag", ["VALVE TAG", "TAG!", "", None])
    def test_tags_autocad_refuses_are_refused_first(self, tag):
        with pytest.raises(AttributeSpecError):
            clean_tag(tag)

    def test_a_space_suggests_an_underscore(self):
        with pytest.raises(AttributeSpecError, match="VALVE_TAG"):
            clean_tag("VALVE TAG")

    def test_the_same_tag_twice_is_refused_whatever_the_case(self):
        with pytest.raises(AttributeSpecError, match="twice"):
            plan_definitions([{"tag": "TAG"}, {"tag": "tag"}], [0, 0], 2.5)

    def test_a_tag_the_block_already_has_is_refused(self):
        with pytest.raises(AttributeSpecError, match="twice"):
            plan_definitions([{"tag": "SIZE"}], [0, 0], 2.5, taken=["size"])

    def test_an_unknown_key_is_named(self):
        with pytest.raises(AttributeSpecError, match="colour"):
            plan_definitions([{"tag": "TAG", "colour": 1}], [0, 0], 2.5)


class TestConstantAndPreset:
    def test_constant_needs_a_value(self):
        with pytest.raises(AttributeSpecError, match="no default"):
            plan_definitions([{"tag": "MAKE", "constant": True}], [0, 0], 2.5)

    def test_constant_and_preset_together_is_refused(self):
        with pytest.raises(AttributeSpecError, match="Pick one"):
            plan_definitions([{"tag": "MAKE", "default": "X", "constant": True, "preset": True}], [0, 0], 2.5)

    def test_value_is_another_word_for_default(self):
        (one,) = plan_definitions([{"tag": "TAG", "value": "V-1"}], [0, 0], 2.5)
        assert one["default"] == "V-1"


class TestPlaceAndSize:
    def test_no_position_stacks_them_under_the_base_point(self):
        first, second = plan_definitions([{"tag": "A"}, {"tag": "B"}], [100, 200], 10.0)
        assert first["position"] == [100.0, 200.0 - STACK_GAP * 10.0, 0.0]
        assert second["position"] == [100.0, 200.0 - 2 * STACK_GAP * 10.0, 0.0]

    def test_a_given_position_is_kept_and_only_the_others_stack(self):
        placed, stacked = plan_definitions([{"tag": "A", "position": [5, 6]}, {"tag": "B"}], [0, 0], 2.0)
        assert placed["position"] == [5.0, 6.0, 0.0]
        assert stacked["position"] == [0.0, -STACK_GAP * 2.0, 0.0]

    def test_the_height_defaults_to_the_drawings_text_size(self):
        (one,) = plan_definitions([{"tag": "A"}], [0, 0], 25.0)
        assert one["height"] == 25.0

    def test_a_drawing_with_no_text_size_still_gets_a_height(self):
        (one,) = plan_definitions([{"tag": "A"}], [0, 0], 0.0)
        assert one["height"] > 0

    @pytest.mark.parametrize("height", [0, -1, "big"])
    def test_a_bad_height_is_refused(self, height):
        with pytest.raises(AttributeSpecError, match="height"):
            plan_definitions([{"tag": "A", "height": height}], [0, 0], 2.5)

    def test_new_ones_stack_under_the_attributes_already_there(self):
        """Review 2026-11-21: added later, SIZE went on top of TAG, which make_block had stacked."""
        (size,) = plan_definitions([{"tag": "SIZE"}], [0, 0], 10.0, taken=["TAG", "REV"], taken_at=[[0, -15, 0], [40, 5, 0]])
        assert size["position"] == [0.0, -15.0 - STACK_GAP * 10.0, 0.0]

    def test_the_prompt_defaults_to_the_tag(self):
        (one,) = plan_definitions([{"tag": "size"}], [0, 0], 2.5)
        assert one["prompt"] == "SIZE"


# ---------------------------------------------------------------------------
# ATTSYNC
# ---------------------------------------------------------------------------

DEFINITION = [
    {"tag": "TAG", "default": "V-?"},
    {"tag": "SIZE", "default": "DN50"},
    {"tag": "MAKE", "default": "ACME", "constant": True},
]


class TestSyncOne:
    def test_a_typed_value_is_kept_and_a_new_tag_comes_in_with_its_default(self):
        plan = sync_one(DEFINITION, [("TAG", "V-101")])
        assert plan["keep"] == {"TAG": "V-101"}
        assert plan["add"] == {"SIZE": "DN50"}
        assert plan["drop"] == []
        assert plan["attributes"] == [("TAG", "V-101"), ("SIZE", "DN50")]
        assert plan["changes_tags"]

    def test_a_tag_the_definition_lost_goes_with_its_value(self):
        plan = sync_one(DEFINITION, [("TAG", "V-1"), ("SIZE", "DN80"), ("OLD", "x")])
        assert plan["drop"] == ["OLD"] and plan["dropped"] == [("OLD", "x")]
        assert plan["keep"] == {"TAG": "V-1", "SIZE": "DN80"}

    def test_a_tag_made_constant_goes_from_the_insert(self):
        plan = sync_one(DEFINITION, [("TAG", "V-1"), ("SIZE", "DN80"), ("MAKE", "OTHER")])
        assert plan["drop"] == ["MAKE"]
        assert "MAKE" not in plan["keep"] and "MAKE" not in plan["add"]

    def test_tags_match_whatever_the_case(self):
        plan = sync_one(DEFINITION, [("tag", "V-7"), ("Size", "DN25")])
        assert plan["keep"] == {"TAG": "V-7", "SIZE": "DN25"} and not plan["changes_tags"]

    def test_an_insert_already_in_step_changes_no_tag(self):
        plan = sync_one(DEFINITION, [("TAG", "V-1"), ("SIZE", "DN80")])
        assert not plan["changes_tags"] and not plan["add"] and not plan["drop"]

    def test_a_tag_given_twice_is_matched_in_order(self):
        definition = [{"tag": "LINE", "default": ""}, {"tag": "LINE", "default": ""}]
        plan = sync_one(definition, [("LINE", "first"), ("LINE", "second"), ("LINE", "third")])
        assert plan["attributes"] == [("LINE", "first"), ("LINE", "second")]
        assert plan["dropped"] == [("LINE", "third")]

    def test_the_inserts_order_is_kept_and_new_ones_follow(self):
        """As the plug-in does it: kept attributes stay in place, new ones go at the end."""
        definition = [{"tag": "SIZE", "default": "DN50"}, {"tag": "FLOW", "default": "0"}, {"tag": "TAG", "default": ""}]
        plan = sync_one(definition, [("TAG", "V-1"), ("SIZE", "DN80")])
        assert plan["attributes"] == [("TAG", "V-1"), ("SIZE", "DN80"), ("FLOW", "0")]

    def test_a_different_order_alone_changes_no_tag(self):
        definition = [{"tag": "SIZE"}, {"tag": "TAG"}]
        plan = sync_one(definition, [("TAG", "V-1"), ("SIZE", "DN80")])
        assert not plan["changes_tags"] and plan["attributes"] == [("TAG", "V-1"), ("SIZE", "DN80")]

    def test_a_tag_given_twice_is_counted_every_time(self):
        definition = [{"tag": "LINE", "default": "a"}, {"tag": "LINE", "default": "b"}, {"tag": "LINE", "default": "c"}]
        plan = sync_one(definition, [("LINE", "first")])
        assert plan["kept"] == [("LINE", "first")] and plan["added"] == [("LINE", "b"), ("LINE", "c")]
        totals = plan_sync("B", definition, [{"handle": "1", "block": "B", "layer": "0", "attributes": [("LINE", "first")]}])
        assert (totals["values_kept"], totals["attributes_added"]) == (1, 2)

    def test_an_empty_value_is_still_a_value_and_kept(self):
        plan = sync_one(DEFINITION, [("TAG", ""), ("SIZE", "DN80")])
        assert plan["keep"]["TAG"] == ""


def insert(handle, block="VALVE TAG", layer="M-VALVE", **values):
    return {"handle": handle, "block": block, "layer": layer, "attributes": list(values.items())}


class TestWhichInsertsAreTouched:
    INSERTS = [
        insert("1A", TAG="V-1"),
        insert("1B", TAG="V-2", SIZE="DN80"),
        insert("1C", block="PUMP TAG", TAG="P-1"),
        insert("1D", block="valve tag", TAG="V-3"),  # a dynamic block's *U copy, by its real name
        insert("1E", layer="LOCKED", TAG="V-4"),
    ]

    def test_only_inserts_of_that_block_by_real_name(self):
        plan = plan_sync("VALVE TAG", DEFINITION, self.INSERTS[:4])
        assert [i["handle"] for i in plan["inserts"]] == ["1A", "1B", "1D"]

    def test_every_insert_is_touched_but_only_some_change_tags(self):
        plan = plan_sync("VALVE TAG", DEFINITION, self.INSERTS[:4])
        assert plan["touched"] == 3 and plan["changing_tags"] == 2
        assert plan["values_kept"] == 4 and plan["attributes_added"] == 2

    def test_an_insert_on_a_locked_layer_is_left_out_and_said(self):
        plan = plan_sync("VALVE TAG", DEFINITION, self.INSERTS, locked_layers=["locked"])
        assert "1E" not in [i["handle"] for i in plan["inserts"]]
        assert plan["skipped"] == [{"handle": "1E", "why": "its layer 'LOCKED' is locked: unlock it first"}]

    def test_handles_narrow_it_and_a_wrong_one_is_said(self):
        plan = plan_sync("VALVE TAG", DEFINITION, self.INSERTS, only=["1b", "1C", "FFF"])
        assert [i["handle"] for i in plan["inserts"]] == ["1B"]
        reasons = {s["handle"]: s["why"] for s in plan["skipped"]}
        assert "PUMP TAG" in reasons["1C"] and "FFF" in reasons

    def test_no_insert_is_an_empty_plan(self):
        plan = plan_sync("VALVE TAG", DEFINITION, [])
        assert plan["touched"] == 0 and plan["inserts"] == []


class TestWildcards:
    @pytest.mark.parametrize(("name", "pattern"), [("PUMP#1", "PUMP`#1"), ("V-101", "V`-101"), ("1.5 TEE", "1`.5 TEE"), ("A,B", "A`,B")])
    def test_a_block_name_is_matched_as_text(self, name, pattern):
        assert blocks.escape_wildcards(name) == pattern

    def test_an_ordinary_name_is_unchanged(self):
        assert blocks.escape_wildcards("VALVE TAG") == "VALVE TAG"


# ---------------------------------------------------------------------------
# The tools against a fake drawing
# ---------------------------------------------------------------------------


class Obj:
    def __init__(self, handle):
        self.Handle, self.deleted = handle, False

    def Delete(self):
        self.deleted = True


class AttDef:
    ObjectName = "AcDbAttributeDefinition"

    def __init__(self, tag, default="", constant=False, at=None):
        self.TagString, self.TextString, self.Constant, self.PromptString = tag, default, constant, tag
        if at is not None:
            self.InsertionPoint = at


class Line:
    ObjectName = "AcDbLine"


class Block:
    def __init__(self, name, items=(), origin=(0.0, 0.0, 0.0)):
        self.Name, self.items, self.Origin = name, list(items), origin
        self.IsLayout = self.IsXRef = False
        self.added = []

    @property
    def Count(self):
        return len(self.items)

    def Item(self, i):
        return self.items[i]

    def AddAttribute(self, height, mode, prompt, at, tag, value):
        self.added.append((height, mode, prompt, tuple(getattr(at, "value", at)), tag, value))


class Blocks:
    def __init__(self, *existing):
        self.items = {b.Name: b for b in existing}
        self.read = 0

    @property
    def Count(self):
        return len(self.items)

    def Item(self, key):
        if isinstance(key, int):
            self.read += 1
            return list(self.items.values())[key]
        return self.items[key]

    def Add(self, base, name):
        self.items[name] = Block(name)
        return self.items[name]


class Ref:
    ObjectName = "AcDbBlockReference"

    def __init__(self, handle, name, layer, values):
        self.Handle, self.Name, self.EffectiveName, self.Layer = handle, name, name, layer
        self.values = values
        self.HasAttributes = bool(values)

    def GetAttributes(self):
        return [type("A", (), {"TagString": t, "TextString": v})() for t, v in self.values]


class Selection:
    def __init__(self, refs):
        self.refs = refs

    @property
    def Count(self):
        return len(self.refs)

    def Item(self, i):
        return self.refs[i]


class Layer:
    def __init__(self, lock=False):
        self.Lock = lock


class Layers:
    def __init__(self, locked=()):
        self.locked = set(locked)

    def Item(self, name):
        return Layer(name in self.locked)


class Space:
    def __init__(self):
        self.inserts = []

    def InsertBlock(self, at, name, *rest):
        ref = Ref("9F", name, "0", [])
        self.inserts.append(ref)
        return ref


class Doc:
    def __init__(self, *existing, refs=(), locked=(), textsize=25.0):
        self.objs = {h: Obj(h) for h in ("1A", "1B")}
        self.Blocks = Blocks(*existing)
        self.ModelSpace = Space()
        self.Layers = Layers(locked)
        self.refs = list(refs)
        self.textsize = textsize
        self.filters = []
        self.set_names = []

    def HandleToObject(self, h):
        return self.objs[h]

    def CopyObjects(self, objects, owner):
        pass

    def GetVariable(self, name):
        return self.textsize if name == "TEXTSIZE" else 0

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


@pytest.fixture
def drawing(monkeypatch):
    holder = {}

    def make(*existing, refs=(), locked=(), textsize=25.0):
        doc = Doc(*existing, refs=refs, locked=locked, textsize=textsize)

        async def run(fn):
            return fn()

        def select(d, entity_type=None, layer=None, block_name=None, color=None, name=None):
            d.filters.append((entity_type, block_name))
            d.set_names.append(name)
            return Selection(d.refs)

        monkeypatch.setattr(blocks, "run", run)
        monkeypatch.setattr(blocks, "get_doc", lambda: doc)
        monkeypatch.setattr(blocks, "require_idle", lambda d: None)
        monkeypatch.setattr(blocks, "get_space", lambda d, s: d.ModelSpace)
        monkeypatch.setattr(blocks, "apply_properties", lambda d, e, layer, aci, lt: {})
        monkeypatch.setattr(blocks, "resolve_handles", lambda d, hs: [d.HandleToObject(h) for h in hs])
        monkeypatch.setattr(blocks, "select_filtered", select)
        monkeypatch.setattr(blocks, "discard_selection_set", lambda d, n=None: None)
        holder["doc"] = doc
        return doc

    return make


def call(coroutine) -> dict:
    text = asyncio.run(coroutine)
    assert not text.startswith("Error:"), text
    return json.loads(text)


class TestMakeBlockWithAttributes:
    def test_the_definitions_go_into_the_new_block_in_order(self, drawing):
        doc = drawing()
        result = call(blocks.autocad_make_block(
            name="VALVE TAG", handles=["1A"], base_point=[0, 0],
            attributes=[{"tag": "tag", "prompt": "Valve tag", "default": "V-101", "position": [10, -20], "height": 25},
                        {"tag": "SIZE", "default": "DN50", "invisible": True}],
        ))  # fmt: skip
        added = doc.Blocks.Item("VALVE TAG").added
        assert added[0] == (25.0, 0, "Valve tag", (10.0, -20.0, 0.0), "TAG", "V-101")
        assert added[1][1] == MODE_INVISIBLE and added[1][4] == "SIZE" and added[1][0] == 25.0
        assert [a["tag"] for a in result["attributes"]] == ["TAG", "SIZE"]
        assert result["attributes"][1]["invisible"] is True

    def test_a_bad_attribute_is_refused_before_anything_is_made(self, drawing):
        doc = drawing()
        text = asyncio.run(blocks.autocad_make_block(
            name="VALVE TAG", handles=["1A"], base_point=[0, 0], attributes=[{"tag": "VALVE TAG"}],
        ))  # fmt: skip
        assert text.startswith("Error:") and "space" in text and "Nothing was made" in text
        assert "VALVE TAG" not in doc.Blocks.items and not doc.objs["1A"].deleted

    def test_no_attributes_is_the_block_it_always_was(self, drawing):
        doc = drawing()
        result = call(blocks.autocad_make_block(name="PLATE", handles=["1A"], base_point=[0, 0]))
        assert "attributes" not in result and doc.Blocks.Item("PLATE").added == []


VALVE = Block("VALVE TAG", [Line(), AttDef("TAG", "V-?"), AttDef("SIZE", "DN50"), AttDef("MAKE", "ACME", constant=True)])


class TestSyncTool:
    def refs(self):
        return [
            Ref("1A", "VALVE TAG", "M-VALVE", [("TAG", "V-1")]),
            Ref("1B", "VALVE TAG", "LOCKED", [("TAG", "V-2")]),
            Ref("1C", "PUMP TAG", "M-PUMP", [("TAG", "P-1")]),
        ]

    def test_a_dry_run_says_what_each_insert_keeps_and_gains_and_sends_nothing(self, drawing, monkeypatch):
        drawing(VALVE, refs=self.refs(), locked=["LOCKED"])
        sent = []
        monkeypatch.setattr(blocks, "in_plugin", lambda *a, **k: sent.append(a))
        result = call(blocks.autocad_sync_attributes(block="VALVE TAG", dry_run=True))
        assert sent == [] and result["dry_run"] is True
        assert result["inserts"] == [{"handle": "1A", "keep": {"TAG": "V-1"}, "add": {"SIZE": "DN50"}, "drop": []}]
        assert result["skipped"][0]["handle"] == "1B"

    def test_the_plug_in_gets_the_block_and_only_the_inserts_it_may_touch(self, drawing, monkeypatch):
        doc = drawing(VALVE, refs=self.refs(), locked=["LOCKED"])
        sent = []

        def plugin(operation, args, what, **kw):
            sent.append((operation, args))
            return {"touched": 1, "values_kept": 1, "attributes_added": 1}

        monkeypatch.setattr(blocks, "in_plugin", plugin)
        result = call(blocks.autocad_sync_attributes(block="VALVE TAG"))
        assert sent == [("sync_attributes", {"block": "VALVE TAG", "handles": ["1A"], "add": []})]
        assert result["synced"]["touched"] == 1
        assert result["before_after"] == [{"handle": "1A", "property": "attribute SIZE", "from": None, "to": "DN50"}]
        # The selection asks for the block's own name and a dynamic block's *U copies,
        # in the shared scratch set: a named set of its own costs an undo step.
        assert doc.filters == [("insert", "VALVE TAG,`*U*")] and doc.set_names == [None]

    def test_new_definitions_are_measured_from_the_base_point(self, drawing, monkeypatch):
        block = Block("PUMP", [AttDef("TAG", "P-?")], origin=(100.0, 50.0, 0.0))
        drawing(block, refs=[Ref("2A", "PUMP", "0", [("TAG", "P-1")])], textsize=10.0)
        sent = []
        monkeypatch.setattr(blocks, "in_plugin", lambda op, args, what, **k: sent.append(args) or {})
        result = call(blocks.autocad_sync_attributes(
            block="PUMP", add_attributes=[{"tag": "MAKE", "default": "GRUNDFOS", "position": [0, -30], "invisible": True}],
        ))  # fmt: skip
        (add,) = sent[0]["add"]
        assert add["position"] == [100.0, 20.0, 0.0] and add["invisible"] is True and add["height"] == 10.0
        assert result["definitions_added"] == ["MAKE"]
        assert result["inserts"][0]["add"] == {"MAKE": "GRUNDFOS"}

    def test_a_new_one_with_no_position_goes_under_the_existing_ones(self, drawing, monkeypatch):
        block = Block("TAGGED", [AttDef("TAG", "", at=(0.0, -37.5, 0.0))])
        drawing(block, refs=[], textsize=25.0)
        sent = []
        monkeypatch.setattr(blocks, "in_plugin", lambda op, args, what, **k: sent.append(args) or {})
        call(blocks.autocad_sync_attributes(block="TAGGED", add_attributes=[{"tag": "SIZE"}]))
        assert sent[0]["add"][0]["position"] == [0.0, -75.0, 0.0]

    @pytest.mark.parametrize("position", [[5], [1, 2, 3, 4], ["a", "b"]])
    def test_a_bad_position_is_refused_plainly(self, drawing, monkeypatch, position):
        drawing(VALVE, refs=self.refs())
        monkeypatch.setattr(blocks, "in_plugin", lambda *a, **k: pytest.fail("nothing may be sent"))
        text = asyncio.run(blocks.autocad_sync_attributes(block="VALVE TAG", add_attributes=[{"tag": "FLOW", "position": position}]))
        assert text.startswith("Error: Attribute 1: the position") and "Nothing was changed" in text

    def test_a_new_tag_the_block_has_is_refused_before_anything_changes(self, drawing, monkeypatch):
        drawing(VALVE, refs=self.refs())
        sent = []
        monkeypatch.setattr(blocks, "in_plugin", lambda *a, **k: sent.append(a))
        text = asyncio.run(blocks.autocad_sync_attributes(block="VALVE TAG", add_attributes=[{"tag": "size"}]))
        assert text.startswith("Error:") and "twice" in text and sent == []

    def test_a_block_that_is_not_there_points_at_the_list(self, drawing):
        drawing()
        text = asyncio.run(blocks.autocad_sync_attributes(block="NOPE"))
        assert text.startswith("Error:") and "autocad_list_blocks" in text

    def test_nothing_to_sync_sends_nothing(self, drawing, monkeypatch):
        drawing(VALVE, refs=[])
        sent = []
        monkeypatch.setattr(blocks, "in_plugin", lambda *a, **k: sent.append(a))
        result = call(blocks.autocad_sync_attributes(block="VALVE TAG"))
        assert sent == [] and result["synced"] is None and "Nothing was changed" in result["note"]


class TestNestedInserts:
    """Issue #156: a tag block inside another block's definition."""

    def skid(self):
        skid = Block("SKID", [Line(), Ref("5A", "VALVE TAG", "0", [("TAG", "V-9")])])
        layout = Block("*Paper_Space", [Ref("5B", "VALVE TAG", "0", [])])
        layout.IsLayout = True
        xref = Block("SITE", [Ref("5C", "VALVE TAG", "0", [])])
        xref.IsXRef = True
        anonymous = Block("*U7", [Ref("5D", "VALVE TAG", "0", [])])
        return [skid, layout, xref, anonymous]

    def test_they_are_left_alone_unless_asked(self, drawing, monkeypatch):
        doc = drawing(VALVE, *self.skid(), refs=[Ref("1A", "VALVE TAG", "0", [("TAG", "V-1")])])
        monkeypatch.setattr(blocks, "in_plugin", lambda *a, **k: pytest.fail("a dry run sends nothing"))
        result = call(blocks.autocad_sync_attributes(block="VALVE TAG", dry_run=True))
        assert [i["handle"] for i in result["inserts"]] == ["1A"] and doc.Blocks.read == 0

    def test_nested_ones_are_found_inside_ordinary_blocks_only(self, drawing, monkeypatch):
        drawing(VALVE, *self.skid(), refs=[Ref("1A", "VALVE TAG", "0", [("TAG", "V-1")])])
        sent = []
        monkeypatch.setattr(blocks, "in_plugin", lambda op, args, what, **k: sent.append(args) or {})
        result = call(blocks.autocad_sync_attributes(block="VALVE TAG", nested=True))
        assert sent[0]["handles"] == ["1A", "5A"]
        nested = result["inserts"][1]
        assert nested == {"handle": "5A", "inside": "SKID", "keep": {"TAG": "V-9"}, "add": {"SIZE": "DN50"}, "drop": []}

    def test_the_plan_says_which_block_holds_it(self):
        plan = plan_sync("VALVE TAG", DEFINITION, [{**insert("5A", TAG="V-9"), "inside": "SKID"}])
        assert plan["inserts"][0]["inside"] == "SKID"


def test_levels():
    assert risk_of("autocad_make_block") is Risk.CHANGE
    assert risk_of("autocad_sync_attributes") is Risk.CHANGE
