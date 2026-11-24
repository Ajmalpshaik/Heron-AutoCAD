"""The facts autocad_check_standards' entity rules read, done by the plug-in in one go (#196, D-145), no AutoCAD.

Over COM the check reads 3-6 properties per object, up to 20,000 objects. The
plug-in reads them in one go (entity_properties); the rules stay in Python. The
answer must be the same either way, so each check runs twice over one fake
drawing, once through a fake plug-in and once over fake COM, and the two answers
are compared as text.

The fake plug-in writes rows the way StandardFacts.cs writes them, numbers as
Utf8JsonWriter does: a whole-number double goes over the pipe as 100, which
Python reads back as an int. PropertyFactsTests.cs holds the C# side to that.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
from pathlib import Path

import pytest

from autocad_mcp.core import bridge
from autocad_mcp.core.bridge import OLD_PLUGIN, READS_1_9, READS_SINCE, BridgeRefused
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import _shared, standards

ROOT = Path(__file__).resolve().parents[1]
OPERATION = "entity_properties"
TRUE_COLOUR = "true colour"


class Layer:
    def __init__(self, name, color=7, linetype="Continuous"):
        self.Name, self.Color, self.Linetype = name, color, linetype
        self.Lineweight, self.LayerOn, self.Freeze, self.Lock, self.Plottable = -3, True, False, False, True


class Layers:
    def __init__(self, layers):
        self.layers = layers
        self.Count = len(layers)

    def Item(self, i):  # noqa: N802 - COM's name
        return self.layers[i]


class Entity:
    """One object of the fake drawing: what COM gives, and what the plug-in reads off the .NET object."""

    def __init__(self, handle, kind, layer, color=256, linetype="ByLayer", box=None):
        self.handle, self.kind, self.layer = handle, kind, layer
        self.color, self.linetype, self.box = color, linetype, box

    def com(self):
        return Com(self)

    def row(self, box_classes):
        """[handle, class, layer, color, linetype, box], as PropertyFact writes it."""
        color = None if self.color == TRUE_COLOUR else self.color
        box = list(self.box) if box_classes and box_classes in self.kind and self.box is not None else None
        return [self.handle, self.kind, self.layer, color, self.linetype, box]


class Com:
    """A COM object: only what COM has; every property read counted."""

    def __init__(self, spec):
        self.spec = spec
        self.reads = 0

    def _read(self, value):
        self.reads += 1
        return value

    Handle = property(lambda self: self._read(self.spec.handle))
    ObjectName = property(lambda self: self._read(self.spec.kind))
    Layer = property(lambda self: self._read(self.spec.layer))
    Linetype = property(lambda self: self._read(self.spec.linetype))

    @property
    def Color(self):  # noqa: N802 - COM's name
        # What COM's Color gives for a true colour is not looked at yet (D-145): this fake says 5.
        return self._read(5 if self.spec.color == TRUE_COLOUR else self.spec.color)

    def GetBoundingBox(self):  # noqa: N802 - COM's name
        self.reads += 1
        if self.spec.box is None:
            raise RuntimeError("no extents")
        x1, y1, x2, y2 = self.spec.box
        return (x1, y1, 0.0), (x2, y2, 0.0)


def drawing():
    return [
        Entity("2A", "AcDbLine", "0"),
        Entity("2B", "AcDbLine", "M-PIPE", color=1),
        Entity("2C", "AcDbCircle", "M-PIPE", linetype="DASHED"),
        Entity("2D", "AcDbRotatedDimension", "A-DIMS", box=(0.0, 0.0, 100.0, 10.0)),
        Entity("2E", "AcDbAlignedDimension", "A-DIMS", box=(50.0, 5.0, 150.5, 12.123456789)),  # overlaps 2D
        Entity("2F", "AcDbRadialDimension", "0", color=0, linetype="ByBlock", box=None),  # no box
        Entity("30", "AcDbPolyline", "E-POWER", color=3, linetype="CENTER"),
        Entity("31", "AcDbRotatedDimension", "A-DIMS", box=(500.0, 500.0, 600.0, 510.0)),
        Entity("32", "AcDbText", "0", color=256, linetype="bylayer"),
    ]


def wire(value):
    """What Utf8JsonWriter sends and Python reads back: a whole-number double becomes an int."""
    if isinstance(value, float):
        if not math.isfinite(value):
            return "not finite"
        return int(value) if value.is_integer() else value
    if isinstance(value, (list, tuple)):
        return [wire(v) for v in value]
    if isinstance(value, dict):
        return {k: wire(v) for k, v in value.items()}
    return value


class Doc:
    def __init__(self, objects):
        self.FullName = r"C:\Project\M-101.dwg"
        self.objects = objects
        self.Layers = Layers([Layer("0"), Layer("A-DIMS", 2), Layer("M-PIPE", 4), Layer("E-POWER", 1, "CENTER")])
        self.com_selections = 0


class FakePlugin:
    """The plug-in's entity_properties, written the way StandardFacts.cs writes it."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.fail: Exception | None = None
        self.answer = None  # replaces the answer when set
        self.specs = drawing()
        self.reset()

    def reset(self):
        self.doc = Doc([s.com() for s in self.specs])

    def __call__(self, operation, args):
        self.calls.append((operation, json.loads(json.dumps(args))))  # what goes over the pipe
        if self.fail:
            raise self.fail
        assert operation == OPERATION, operation
        assert args["filter"] == []  # all of the drawing, as the COM selection
        limit = args["limit"]
        rows = [s.row(args.get("box_classes", "")) for s in self.specs][:limit]
        found = {"entities": rows, "total": len(self.specs)}
        if self.answer is not None:
            found = self.answer(found)
        return json.loads(json.dumps(wire(found)))


@pytest.fixture
def cad(monkeypatch):
    plugin = FakePlugin()

    async def run(fn):
        return fn()

    def select_filtered(doc_, entity_type=None, layer=None, block_name=None, color=None, name=None):
        assert (entity_type, layer, block_name, color, name) == (None, None, None, None, None)
        doc_.com_selections += 1
        return list(doc_.objects)

    monkeypatch.setattr(standards, "run", run)
    monkeypatch.setattr(standards, "get_doc", lambda: plugin.doc)
    monkeypatch.setattr(standards, "select_filtered", select_filtered)
    monkeypatch.setattr(standards, "iter_selection", lambda sel: iter(list(sel)))
    monkeypatch.setattr(standards, "discard_selection_set", lambda d, name=None: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: plugin)
    monkeypatch.setattr(_shared, "plugin_version", lambda: READS_SINCE)
    plugin.use = lambda on: monkeypatch.setattr(_shared, "plugin_runner", (lambda: plugin) if on else (lambda: None))
    return plugin


def answer(coro) -> str:
    text = asyncio.run(coro)
    assert not text.startswith("Error"), text
    return text


def com_reads(cad) -> int:
    return sum(obj.reads for obj in cad.doc.objects)


def both(cad, make) -> tuple[str, str]:
    """The check's answer through the plug-in, then over COM, each on a fresh drawing, as text."""
    cad.reset()
    cad.use(True)
    by_plugin = answer(make())
    assert cad.calls, "the plug-in was not asked"
    assert cad.doc.com_selections == 0 and com_reads(cad) == 0, "the plug-in path read over COM as well"
    asked = len(cad.calls)
    cad.reset()
    cad.use(False)
    by_com = answer(make())
    assert len(cad.calls) == asked
    assert cad.doc.com_selections == 1
    return by_plugin, by_com


def fell_back(cad, make) -> None:
    """The plug-in was asked, its answer not used: the check read over COM, with COM's own answer."""
    cad.reset()
    cad.use(True)
    by_fallback = answer(make())
    assert cad.calls and cad.doc.com_selections == 1
    cad.reset()
    cad.use(False)
    assert by_fallback == answer(make())


ALL = {"forbid_entities_on_layer_0": True, "require_bylayer_color": True, "require_bylayer_linetype": True,
       "forbid_overlapping_dimensions": True}
CHECKS = [
    {"rules": {"forbid_entities_on_layer_0": True}},
    {"rules": {"require_bylayer_color": True}},
    {"rules": {"require_bylayer_linetype": True}},
    {"rules": {"forbid_overlapping_dimensions": True}},
    {"rules": ALL},
    {"rules": {**ALL, "layer_name_pattern": "^[A-Z]-", "layers": {"M-PIPE": {"color": 4}}}},
    {"rules": {**ALL, "max_findings": 3}},
    {"rules": ALL, "max_entities": 4},  # only part read: not decided
    {"rules": ALL, "max_entities": 9},  # exactly all
    {"rules": ALL, "max_entities": 8},  # one left out
    {"rules": {"forbid_entities_on_layer_0": True}, "max_entities": 1},
]


def ids(options):
    return ",".join(f"{k}={v}" for k, v in options.items())


class TestTheSameEitherWay:
    @pytest.mark.parametrize("options", CHECKS, ids=[f"check{i}" for i in range(len(CHECKS))])
    def test_check_standards(self, cad, options):
        by_plugin, by_com = both(cad, lambda: standards.autocad_check_standards(**options))
        assert by_plugin == by_com

    def test_what_it_finds_is_what_com_finds(self, cad):
        out = json.loads(answer(standards.autocad_check_standards(rules=ALL)))
        assert out["checked"]["entities"] == 9 and out["passed"] is False
        assert out["summary"] == {"entity_on_layer_0": 3, "bylayer_color": 3, "bylayer_linetype": 3,
                                  "dimension_overlap": 1}
        overlap = [f for f in out["findings"] if f["rule"] == "dimension_overlap"]
        assert overlap == [{"handle": "2D", "other": "2E", "type": "dimension", "rule": "dimension_overlap",
                            "detail": "overlaps dimension 2E"}]

    def test_only_part_read_is_not_decided_either_way(self, cad):
        cad.specs = [Entity("2A", "AcDbLine", "M-PIPE"), Entity("2B", "AcDbLine", "M-PIPE"),
                     Entity("2C", "AcDbLine", "0")]
        by_plugin, by_com = both(cad, lambda: standards.autocad_check_standards(rules=ALL, max_entities=2))
        assert by_plugin == by_com
        out = json.loads(by_plugin)
        assert out["passed"] is None and "Only the first 2 objects were read" in out["warning"]
        assert cad.calls[-1][1]["limit"] == 3  # one past, so the same loop sees there are more

    def test_a_true_colour_is_read_by_the_plugin_when_no_rule_needs_the_colour(self, cad):
        cad.specs = [*drawing(), Entity("40", "AcDbLine", "0", color=TRUE_COLOUR, linetype="DASHED")]
        rules = {"forbid_entities_on_layer_0": True, "require_bylayer_linetype": True}
        by_plugin, by_com = both(cad, lambda: standards.autocad_check_standards(rules=rules))
        assert by_plugin == by_com

    def test_nothing_in_the_drawing_is_said_the_same_way(self, cad):
        cad.specs = []
        by_plugin, by_com = both(cad, lambda: standards.autocad_check_standards(rules=ALL))
        assert by_plugin == by_com and json.loads(by_plugin)["passed"] is True


class TestWhatIsSent:
    def test_all_of_the_drawing_one_past_the_cut_off(self, cad):
        answer(standards.autocad_check_standards(rules={"forbid_entities_on_layer_0": True}))
        assert cad.calls[-1] == (OPERATION, {"filter": [], "limit": 20001})

    def test_boxes_only_when_the_overlap_rule_is_asked(self, cad):
        answer(standards.autocad_check_standards(rules={"forbid_overlapping_dimensions": True}, max_entities=50))
        assert cad.calls[-1] == (OPERATION, {"filter": [], "limit": 51, "box_classes": "Dimension"})

    def test_no_entity_rule_asks_nothing(self, cad):
        answer(standards.autocad_check_standards(rules={"layer_name_pattern": "^[A-Z]-"}))
        assert cad.calls == [] and cad.doc.com_selections == 0

    def test_over_com_only_the_facts_a_rule_needs_are_read(self, cad):
        cad.use(False)
        answer(standards.autocad_check_standards(rules={"forbid_entities_on_layer_0": True}))
        assert com_reads(cad) == 3 * len(cad.specs)  # handle, class, layer: no colour or linetype


BAD_ANSWERS = {
    "no entities": lambda found: {"total": found["total"]},
    "no total": lambda found: {"entities": found["entities"]},
    "total a flag": lambda found: {**found, "total": True},
    "one left out": lambda found: {**found, "entities": found["entities"][1:]},
    "short row": lambda found: {**found, "entities": [r[:5] for r in found["entities"]]},
    "layer not text": lambda found: {**found, "entities": [[r[0], r[1], None, *r[3:]] for r in found["entities"]]},
    "colour a flag": lambda found: {**found, "entities": [[*r[:3], True, *r[4:]] for r in found["entities"]]},
    "colour out of range": lambda found: {**found, "entities": [[*r[:3], 300, *r[4:]] for r in found["entities"]]},
    "box not finite": lambda found: {**found, "entities": [
        [*r[:5], [math.nan, 0.0, 1.0, 1.0]] if r[5] else r for r in found["entities"]]},
    "box short": lambda found: {**found, "entities": [[*r[:5], r[5][:3]] if r[5] else r for r in found["entities"]]},
}


class TestFallsBackToCom:
    @pytest.mark.parametrize(
        "refusal",
        [
            BridgeRefused(OLD_PLUGIN),
            # Plug-ins 1.8.0 and 1.8.1, and one built before this read, pass READS_SINCE but have no entity_properties.
            BridgeRefused(
                "Heron in AutoCAD does not have the operation 'entity_properties'. Update Heron so both sides "
                "match. Nothing was sent to AutoCAD."
            ),
            AutocadError("Heron could not read an object it selected. Nothing was changed."),
        ],
    )
    def test_a_plugin_that_cannot_read_it_hands_over_to_com(self, cad, refusal):
        cad.fail = refusal
        fell_back(cad, lambda: standards.autocad_check_standards(rules=ALL))
        assert len(cad.calls) == 1

    def test_an_older_plugin_is_not_asked(self, cad, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_version", lambda: "1.7.0")
        answer(standards.autocad_check_standards(rules=ALL))
        assert cad.calls == [] and cad.doc.com_selections == 1

    @pytest.mark.parametrize("bad", list(BAD_ANSWERS), ids=list(BAD_ANSWERS))
    def test_an_answer_this_server_cannot_read_as_com_is_not_used(self, cad, bad):
        cad.answer = BAD_ANSWERS[bad]
        fell_back(cad, lambda: standards.autocad_check_standards(rules=ALL))

    def test_a_true_colour_the_colour_rule_needs_is_read_over_com(self, cad):
        cad.specs = [*drawing(), Entity("40", "AcDbLine", "M-PIPE", color=TRUE_COLOUR)]
        fell_back(cad, lambda: standards.autocad_check_standards(rules={"require_bylayer_color": True}))

    def test_a_true_colour_past_the_cut_off_is_not_read_so_the_plugin_answer_stands(self, cad):
        cad.specs = [*drawing(), Entity("40", "AcDbLine", "M-PIPE", color=TRUE_COLOUR)]
        by_plugin, by_com = both(cad, lambda: standards.autocad_check_standards(
            rules={"require_bylayer_color": True}, max_entities=9))
        assert by_plugin == by_com

    @pytest.mark.parametrize(
        "refusal",
        [
            AutocadError(bridge.RUN_UNKNOWN.format(seconds=300, details="no answer")),
            BridgeRefused("The modeller pressed Stop in AutoCAD (HERONSTOP). Nothing was sent to AutoCAD."),
        ],
    )
    def test_a_stop_or_no_answer_is_said_not_read_again_over_com(self, cad, refusal):
        cad.fail = refusal
        assert asyncio.run(standards.autocad_check_standards(rules=ALL)).startswith("Error")
        assert cad.doc.com_selections == 0


class TestBothSidesKnowTheRead:
    def test_the_plugin_lists_and_dispatches_it(self):
        listed = (ROOT / "autocad" / "Heron.AutoCAD.Bridge" / "PluginOperations.cs").read_text(encoding="utf-8")
        runner = (ROOT / "autocad" / "Heron.AutoCAD.Addin" / "PluginRunner.cs").read_text(encoding="utf-8")
        assert f'["{OPERATION}"] = Risk.Read' in listed
        assert f'case "{OPERATION}":' in runner

    def test_the_server_asks_for_it_and_names_it_newer(self):
        source = (ROOT / "src" / "autocad_mcp" / "tools" / "standards.py").read_text(encoding="utf-8")
        assert OPERATION in set(re.findall(r'faster_read\("(\w+)"', source))
        assert OPERATION in READS_1_9

    def test_the_box_test_is_the_same_text_on_both_sides(self):
        facts = (ROOT / "autocad" / "Heron.AutoCAD.Bridge" / "StandardFacts.cs").read_text(encoding="utf-8")
        assert "IndexOf(_boxClasses, StringComparison.Ordinal)" in facts  # as Python's `in`: the case counts
        assert standards.DIMENSION == "Dimension"
