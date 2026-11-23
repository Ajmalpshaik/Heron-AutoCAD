"""Block counts the plug-in reads in one go (#192, #194, D-127), no AutoCAD.

autocad_count_blocks and autocad_list_blocks look at every placed block and
every block definition. COM does that a round trip per property; Heron's
plug-in does it in one go. The answer must be the same either way, so each
tool runs twice over one fake drawing, once through a fake plug-in and once
over fake COM, and the two answers are compared as text.

The fake plug-in answers the way autocad/Heron.AutoCAD.Bridge/BlockTally.cs
writes, down to its JSON: a whole-number double goes over the pipe as 50,
which Python reads back as an int while COM gives 50.0. BlockTallyTests.cs
holds the C# side to that.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import re
from pathlib import Path

import pytest

from autocad_mcp.core import bridge
from autocad_mcp.core.bridge import NEWER_READS, OLD_PLUGIN, READS_SINCE, BridgeRefused
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import _shared, layers, takeoff

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ("block_references", "block_definitions")


class Prop:
    def __init__(self, name, value, read_only=False):
        self.PropertyName, self.ReadOnly, self._value = name, read_only, value

    @property
    def Value(self):  # noqa: N802 - COM's name
        if isinstance(self._value, Exception):
            raise self._value
        return self._value


class Ref:
    def __init__(self, name, layer, effective=None, props=None, kind="AcDbBlockReference"):
        self.Name, self.Layer, self.ObjectName = name, layer, kind
        self.EffectiveName = name if effective is None else effective
        self.props = props
        self.IsDynamicBlock = props is not None

    def GetDynamicBlockProperties(self):  # noqa: N802
        return tuple(self.props or ())


class Item:
    def __init__(self, kind, tag=""):
        self.ObjectName, self.TagString = kind, tag


class Block:
    def __init__(self, name, items=(), layout=False, xref=None, dynamic=False):
        self.Name, self.items, self.IsLayout, self.IsDynamicBlock = name, list(items), layout, dynamic
        self.IsXRef, self.Path = xref is not None, xref or ""

    @property
    def Count(self):  # noqa: N802
        return len(self.items)

    def Item(self, j):  # noqa: N802
        return self.items[j]


class Items(list):
    @property
    def Count(self):  # noqa: N802
        return len(self)

    def Item(self, i):  # noqa: N802
        return self[i]


def valve(name, layer, size, flip=0, visibility="Open", effective="GATE VALVE"):
    return Ref(name, layer, effective, [
        Prop("Size", size),
        Prop("Flip state1", flip),
        Prop("Visibility1", visibility),
        Prop("Origin", (0.0, 0.0, 0.0), read_only=True),
        Prop("Angle", 0.0, read_only=True),
        Prop("Type", "Flanged"),
    ])


ATT = Item("AcDbAttributeDefinition", "TAG")
DESK = Ref("DESK", "A-FURN")
CHAIR = Ref("CHAIR", "A-FURN")

# Placed in the drawing, in the order a selection gives them: dynamic copies
# renamed *U.., whole-number and fractional sizes, flip states, a plain block,
# a MINSERT and a value AutoCAD would not give.
REFS = [
    valve("*U12", "M-PIPE", 50.0),
    valve("GATE VALVE", "M-PIPE", 1.0),
    Ref("ROOM", "A-AREA"),
    valve("*U13", "m-pipe", 50.0, flip=1),
    valve("*U14", "M-PIPE", 1, visibility="Closed"),  # an int where a distance is: kept apart from 1.0
    Ref("DIFFUSER", "M-HVAC"),
    valve("*U12", "M-PIPE", 50.0),
    Ref("DIFFUSER", "M-HVAC", kind="AcDbMInsertBlock"),
    Ref("*U15", "M-PIPE", "GATE VALVE", [Prop("Size", RuntimeError("no value")), Prop("Visibility1", "Open")]),
    Ref("*U16", "M-PIPE", "GATE VALVE", [Prop("Origin", RuntimeError("no value"), read_only=True)]),
    Ref("", "0", ""),
    Ref("ROOM", "A-AREA"),
]

BLOCKS = [
    Block("*Model_Space", [DESK, DESK], layout=True),
    Block("*Paper_Space", [CHAIR], layout=True),
    Block("ROOM", [DESK, Item("AcDbLine"), DESK, Ref("DESK", "A-FURN", kind="AcDbMInsertBlock")]),
    Block("DESK", [CHAIR, ATT, Item("AcDbLine"), Item("AcDbAttributeDefinition", "DESK-NO")]),
    Block("GATE VALVE", [Item("AcDbLine"), ATT], dynamic=True),
    Block("*U12", [Item("AcDbLine")]),
    Block("DIFFUSER", [Item("AcDbCircle")]),
    Block("Unused Block", []),
    Block("", []),
    Block("SITE", [Ref("TREE", "L-PLANT")], xref=r"C:\Project\Site.dwg"),
    Block("SITE|LAMP", [Ref("POLE", "E-LIGHT")]),
    Block("CHAIR", []),
]

DXF = {"AcDbBlockReference": "INSERT", "AcDbMInsertBlock": "INSERT"}


def matches(ref, pairs):
    for code, value in pairs:
        if code == 0 and DXF.get(ref.ObjectName) != value:
            return False
        if code == 8 and not fnmatch.fnmatch(ref.Layer.casefold(), str(value).casefold()):
            return False
    return True


def wire(value):
    """What Utf8JsonWriter sends and Python reads back: a whole-number double becomes an int."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, (list, tuple)):
        return [wire(v) for v in value]
    if isinstance(value, dict):
        return {k: wire(v) for k, v in value.items()}
    return value


def kinded(prop):
    """[kind, value] as DynamicValue.Write sends it."""
    try:
        value = prop.Value
    except Exception:  # noqa: BLE001
        return ["error", None]
    if value is None:
        return ["none", None]
    if isinstance(value, bool):
        return ["other", "Boolean"]
    if isinstance(value, float):
        return ["real", value]
    if isinstance(value, int):
        return ["int", value]
    if isinstance(value, str):
        return ["text", value]
    if isinstance(value, tuple):
        return ["point", list(value)]
    return ["other", type(value).__name__]


def real_name(ref):
    return ref.EffectiveName or ref.Name


class FakePlugin:
    """The plug-in's two block reads, written the way BlockTally.cs writes them."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.fail: Exception | None = None
        self.ignore: set[str] = set()
        self.refs, self.blocks = list(REFS), list(BLOCKS)

    def __call__(self, operation, args):
        self.calls.append((operation, json.loads(json.dumps(args))))  # what goes over the pipe
        if self.fail:
            raise self.fail
        chosen = [r for r in self.refs if matches(r, [tuple(p) for p in args["filter"]])]
        if operation == "block_references":
            out = {"refs": [
                [real_name(r), r.Layer,
                 [[p.PropertyName, p.ReadOnly, *kinded(p)] for p in (r.props if r.IsDynamicBlock else [])]]
                for r in chosen
            ]}
            if args.get("nested") and "nested" not in self.ignore:
                out["children"] = [
                    [b.Name, [[real_name(i), i.Layer] for i in b.items if i.ObjectName == "AcDbBlockReference"]]
                    for b in self.blocks
                    if not b.IsLayout and not b.IsXRef and any(i.ObjectName == "AcDbBlockReference" for i in b.items)
                ]
            return json.loads(json.dumps(wire(out)))
        if operation == "block_definitions":
            out = {"definitions": [
                {"name": b.Name, "count": b.Count, "xref": b.IsXRef, "path": b.Path if b.IsXRef else None,
                 "dynamic": b.IsDynamicBlock,
                 "tags": [i.TagString for i in b.items if i.ObjectName == "AcDbAttributeDefinition"]}
                for b in self.blocks
                if not b.IsLayout and b.Name[:1] not in ("", "*")
            ]}
            if args.get("counts") and "counts" not in self.ignore:
                names: dict[str, int] = {}
                for r in chosen:
                    names[real_name(r)] = names.get(real_name(r), 0) + 1
                out["instances"] = [[k, n] for k, n in names.items()]
            return json.loads(json.dumps(wire(out)))
        raise AssertionError(operation)


class Doc:
    def __init__(self, plugin):
        self.plugin = plugin
        self.com_selections = 0

    @property
    def Blocks(self):  # noqa: N802
        return Items(self.plugin.blocks)


@pytest.fixture
def cad(monkeypatch):
    plugin = FakePlugin()
    doc = Doc(plugin)

    async def run(fn):
        return fn()

    def select_filtered(doc_, entity_type=None, layer=None, block_name=None, color=None, **kw):
        doc_.com_selections += 1
        assert entity_type in ("insert", "block") and block_name is None and color is None
        pairs = [(0, "INSERT")] + ([(8, layer.strip())] if layer else [])
        return Items(r for r in plugin.refs if matches(r, pairs))

    for module in (takeoff, layers):
        monkeypatch.setattr(module, "run", run)
        monkeypatch.setattr(module, "get_doc", lambda: doc)
        monkeypatch.setattr(module, "select_filtered", select_filtered)
        monkeypatch.setattr(module, "iter_selection", lambda sel: iter(list(sel)))
        monkeypatch.setattr(module, "discard_selection_set", lambda d, name=None: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: plugin)
    monkeypatch.setattr(_shared, "plugin_version", lambda: READS_SINCE)
    plugin.use = lambda on: monkeypatch.setattr(_shared, "plugin_runner", (lambda: plugin) if on else (lambda: None))
    plugin.doc = doc
    return plugin


def answer(coro) -> str:
    text = asyncio.run(coro)
    assert not text.startswith("Error"), text
    return text


def both(cad, make) -> tuple[str, str]:
    """The tool's answer through the plug-in, then over COM, as text."""
    cad.use(True)
    by_plugin = answer(make())
    assert cad.calls, "the plug-in was not asked"
    assert cad.doc.com_selections == 0, "the plug-in path read over COM as well"
    asked = len(cad.calls)
    cad.use(False)
    by_com = answer(make())
    assert len(cad.calls) == asked
    return by_plugin, by_com


COUNTS = [
    {"group_by": group_by, **extra}
    for group_by in ("name", "name_layer", "name_visibility", "name_properties")
    for extra in ({}, {"include_nested": True}, {"layer": "M-*"}, {"block_name": "gate*"},
                  {"layer": "m-pipe", "include_nested": True}, {"layer": "NOTHING-HERE"})
]


class TestTheWireIsWhatTheTrapIsAbout:
    def test_a_whole_number_distance_comes_over_as_an_int(self, cad):
        # Without the kind, 50.0 would be counted as 50: a count by size split in two (#192).
        read = cad("block_references", {"filter": [[0, "INSERT"]]})
        size = read["refs"][0][2][0]
        assert size == ["Size", False, "real", 50] and isinstance(size[3], int)


class TestCountBlocksTheSameEitherWay:
    @pytest.mark.parametrize("options", COUNTS, ids=lambda o: ",".join(f"{k}={v}" for k, v in o.items()))
    def test_count_blocks(self, cad, options):
        by_plugin, by_com = both(cad, lambda: takeoff.autocad_count_blocks(**options))
        assert by_plugin == by_com

    def test_sizes_keep_the_type_com_gives(self, cad):
        rows = json.loads(answer(takeoff.autocad_count_blocks(group_by="name_properties")))["rows"]
        sizes = [(row["properties"]["Size"], row["count"]) for row in rows if "Size" in row["properties"]]
        # 50.0 and 1.0 are distances, 1 is not: three groups, as COM counts them; read-only ones left out.
        assert sorted(sizes, key=repr) == sorted([(50.0, 2), (50.0, 1), (1.0, 1), (1, 1)], key=repr)
        assert {type(size) for size, _ in sizes} == {float, int}
        assert all(set(row["properties"]) <= {"Size", "Flip state1", "Type"} for row in rows)

    def test_a_value_autocad_will_not_give_skips_that_block_both_ways(self, cad):
        out = json.loads(answer(takeoff.autocad_count_blocks()))
        # *U15's Size could not be read (skipped); *U16's Origin is never read (counted).
        assert out["total"] == len(REFS) - 1

    def test_counting_by_name_needs_no_property_value_over_com(self, cad):
        cad.use(False)
        assert json.loads(answer(takeoff.autocad_count_blocks()))["total"] == len(REFS) - 1


class TestWhatCountBlocksSends:
    def test_the_filter_is_the_one_com_selects_with(self, cad):
        answer(takeoff.autocad_count_blocks(layer=" M-* ", block_name="GATE*"))
        assert cad.calls[-1] == ("block_references", {"filter": [[0, "INSERT"], [8, "M-*"]]})

    def test_nested_is_asked_for_only_when_wanted(self, cad):
        answer(takeoff.autocad_count_blocks(include_nested=True))
        assert cad.calls[-1] == ("block_references", {"filter": [[0, "INSERT"]], "nested": True})


class TestCountBlocksFallsBackToCom:
    @pytest.mark.parametrize(
        "refusal",
        [
            BridgeRefused(OLD_PLUGIN),
            # Plug-ins 1.8.0 and 1.8.1 pass READS_SINCE but have no block reads.
            BridgeRefused(
                "Heron in AutoCAD does not have the operation 'block_references'. Update Heron so both sides "
                "match. Nothing was sent to AutoCAD."
            ),
            AutocadError("AutoCAD refused it (eInvalidInput). Nothing was changed."),
            AutocadError("Heron in AutoCAD hit an error: boom Nothing was changed."),
        ],
    )
    def test_a_plugin_that_cannot_read_it_hands_over_to_com(self, cad, refusal):
        cad.fail = refusal
        cad.use(True)
        by_fallback = answer(takeoff.autocad_count_blocks(group_by="name_properties", include_nested=True))
        assert len(cad.calls) == 1 and cad.doc.com_selections == 1
        cad.use(False)
        assert by_fallback == answer(takeoff.autocad_count_blocks(group_by="name_properties", include_nested=True))

    def test_an_older_plugin_is_not_asked(self, cad, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_version", lambda: "1.7.0")
        answer(takeoff.autocad_count_blocks())
        assert cad.calls == [] and cad.doc.com_selections == 1

    def test_a_plugin_that_ignored_nested_is_not_believed(self, cad):
        cad.ignore.add("nested")
        cad.use(True)
        by_fallback = answer(takeoff.autocad_count_blocks(include_nested=True))
        assert len(cad.calls) == 1 and cad.doc.com_selections == 1
        cad.use(False)
        assert by_fallback == answer(takeoff.autocad_count_blocks(include_nested=True))

    def test_a_value_of_a_type_the_server_does_not_know_is_read_over_com(self, cad):
        cad.refs = [*REFS, Ref("*U20", "M-PIPE", "GATE VALVE", [Prop("Size", True)])]
        cad.use(True)
        by_fallback = answer(takeoff.autocad_count_blocks(group_by="name_properties"))
        assert cad.doc.com_selections == 1
        cad.use(False)
        assert by_fallback == answer(takeoff.autocad_count_blocks(group_by="name_properties"))

    def test_an_unknown_type_the_count_does_not_need_is_no_reason_for_com(self, cad):
        # Read-only and not a visibility state: never counted by, so the plug-in's answer stands.
        cad.refs = [*REFS, Ref("*U21", "M-PIPE", "GATE VALVE", [Prop("Base", True, read_only=True)])]
        answer(takeoff.autocad_count_blocks(group_by="name_properties"))
        assert cad.doc.com_selections == 0

    @pytest.mark.parametrize("reply", [{}, {"refs": "none"}, {"refs": [["A", "0"]]}, {"refs": [[1, 2, [["x"]]]]}])
    def test_an_answer_of_the_wrong_shape_is_read_over_com(self, cad, reply, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: lambda operation, args: reply)
        answer(takeoff.autocad_count_blocks())
        assert cad.doc.com_selections == 1

    @pytest.mark.parametrize(
        "refusal",
        [
            AutocadError(bridge.RUN_UNKNOWN.format(seconds=300, details="no answer")),
            BridgeRefused("The modeller pressed Stop in AutoCAD (HERONSTOP). Nothing was sent to AutoCAD."),
        ],
    )
    def test_a_stop_or_no_answer_is_said_not_read_again_over_com(self, cad, refusal):
        cad.fail = refusal
        assert asyncio.run(takeoff.autocad_count_blocks()).startswith("Error")
        assert cad.doc.com_selections == 0


LISTINGS = [{}, {"include_unused": True}, {"include_counts": False}, {"include_counts": False, "include_unused": True}]


class TestListBlocksTheSameEitherWay:
    @pytest.mark.parametrize("options", LISTINGS, ids=lambda o: ",".join(f"{k}={v}" for k, v in o.items()) or "default")
    def test_list_blocks(self, cad, options):
        by_plugin, by_com = both(cad, lambda: layers.autocad_list_blocks(**options))
        assert by_plugin == by_com

    def test_the_listing_says_what_it_should(self, cad):
        listed = {b["name"]: b for b in json.loads(answer(layers.autocad_list_blocks(include_unused=True)))["blocks"]}
        assert set(listed) == {"ROOM", "DESK", "GATE VALVE", "DIFFUSER", "Unused Block", "SITE", "SITE|LAMP", "CHAIR"}
        # *U copies count under the real name; a reference whose real name is blank is not a block's.
        assert listed["GATE VALVE"]["instances"] == 7 and listed["GATE VALVE"]["dynamic"] is True
        assert listed["DIFFUSER"]["instances"] == 2 and listed["ROOM"]["instances"] == 2
        assert listed["DESK"]["attribute_tags"] == ["TAG", "DESK-NO"] and listed["DESK"]["entity_count"] == 4
        assert listed["SITE"]["is_xref"] is True and listed["SITE"]["path"] == r"C:\Project\Site.dwg"
        assert "path" not in listed["ROOM"] and "attribute_tags" not in listed["ROOM"]

    def test_counts_go_by_real_name_without_case(self, cad):
        cad.refs = [Ref("*U30", "0", "gate valve", []), Ref("GATE VALVE", "0")]
        by_plugin, by_com = both(cad, lambda: layers.autocad_list_blocks())
        assert by_plugin == by_com
        assert json.loads(by_plugin)["blocks"] == [
            {"name": "GATE VALVE", "entity_count": 2, "is_xref": False, "dynamic": True,
             "attribute_tags": ["TAG"], "instances": 2}
        ]


class TestWhatListBlocksSends:
    def test_counts_are_asked_for_with_the_insert_filter(self, cad):
        answer(layers.autocad_list_blocks())
        assert cad.calls[-1] == ("block_definitions", {"filter": [[0, "INSERT"]], "counts": True})

    def test_no_counts_no_count_asked_for(self, cad):
        answer(layers.autocad_list_blocks(include_counts=False))
        assert cad.calls[-1] == ("block_definitions", {"filter": [[0, "INSERT"]]})


class TestListBlocksFallsBackToCom:
    def test_an_old_plugin_without_the_operation_hands_over_to_com(self, cad):
        cad.fail = BridgeRefused(
            "Heron in AutoCAD does not have the operation 'block_definitions'. Update Heron so both sides "
            "match. Nothing was sent to AutoCAD."
        )
        cad.use(True)
        by_fallback = answer(layers.autocad_list_blocks())
        assert len(cad.calls) == 1 and cad.doc.com_selections == 1
        cad.use(False)
        assert by_fallback == answer(layers.autocad_list_blocks())

    def test_a_plugin_that_ignored_counts_is_not_believed(self, cad):
        cad.ignore.add("counts")
        cad.use(True)
        by_fallback = answer(layers.autocad_list_blocks())
        assert cad.doc.com_selections == 1
        cad.use(False)
        assert by_fallback == answer(layers.autocad_list_blocks())

    def test_an_older_plugin_is_not_asked(self, cad, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_version", lambda: "1.7.0")
        answer(layers.autocad_list_blocks())
        assert cad.calls == [] and cad.doc.com_selections == 1

    @pytest.mark.parametrize("reply", [{}, {"definitions": [{"name": "A"}]}, {"definitions": [], "instances": [["A"]]}])
    def test_an_answer_of_the_wrong_shape_is_read_over_com(self, cad, reply, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: lambda operation, args: reply)
        answer(layers.autocad_list_blocks())
        assert cad.doc.com_selections == 1

    def test_a_stop_is_said_not_read_again_over_com(self, cad):
        cad.fail = BridgeRefused("The modeller pressed Stop in AutoCAD (HERONSTOP). Nothing was sent to AutoCAD.")
        assert asyncio.run(layers.autocad_list_blocks()).startswith("Error")
        assert cad.doc.com_selections == 0


class TestBothSidesKnowTheBlockReads:
    def test_the_plugin_lists_and_dispatches_both(self):
        listed = (ROOT / "autocad" / "Heron.AutoCAD.Bridge" / "PluginOperations.cs").read_text(encoding="utf-8")
        runner = (ROOT / "autocad" / "Heron.AutoCAD.Addin" / "PluginRunner.cs").read_text(encoding="utf-8")
        for name in OPERATIONS:
            assert f'["{name}"] = Risk.Read' in listed, name
            assert f'case "{name}":' in runner, name

    def test_the_server_asks_for_both_and_names_them_newer(self):
        # takeoff.py asks for entity_lengths too (D-134): tests/test_plugin_length_text_reads.py holds that one.
        asked = set()
        for module in ("takeoff.py", "layers.py"):
            source = (ROOT / "src" / "autocad_mcp" / "tools" / module).read_text(encoding="utf-8")
            asked |= set(re.findall(r'faster_read\("(\w+)"', source))
        assert set(OPERATIONS) <= asked and set(OPERATIONS) <= set(NEWER_READS)
        assert asked - set(OPERATIONS) == {"entity_lengths"}
