"""Reads over a whole drawing that the plug-in does in one go (#74, D-114), no AutoCAD.

autocad_list_entities(summary_only=true) and autocad_get_extents(layer=...)
look at every object they select. COM does that one round trip per object;
Heron's plug-in does it in one go. The answer must be the same either way, so
each tool here runs twice over one fake drawing, once through a fake plug-in
and once over fake COM, and the two answers are compared as text.

The fake plug-in counts the way autocad/Heron.AutoCAD.Bridge/EntityTally.cs
counts (class names as COM's ObjectName gives them, in the order first met,
the box at full precision); EntityReadsTests.cs holds the C# side to that.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import re
from pathlib import Path

import pytest

from autocad_mcp.acad.entities import OBJECT_NAME_MAP, short_type, short_type_name
from autocad_mcp.acad.selection import ENTITY_TYPE_ALIASES, build_filter, filter_pairs
from autocad_mcp.core import bridge, gate
from autocad_mcp.core.bridge import (
    NEWER_READS,
    OLD_PLUGIN,
    READS_1_9,
    READS_1_9_SINCE,
    READS_SINCE,
    BridgeRefused,
    older,
)
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import _shared, query

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ("count_entities", "entity_extents")


class Entity:
    def __init__(self, name, layer, box=None, block=None, color=256):
        self.ObjectName = name
        self.Layer = layer
        self.box = box
        self.Name = block
        self.Color = color

    def GetBoundingBox(self):  # noqa: N802 - COM's name
        if self.box is None:
            raise RuntimeError("no extents")  # a ray or a construction line
        return self.box


# DXF names the filter matches on, by class: what AutoCAD itself does.
DXF = {
    "AcDbLine": "LINE",
    "AcDbPolyline": "LWPOLYLINE",
    "AcDbCircle": "CIRCLE",
    "AcDbBlockReference": "INSERT",
    "AcDbRotatedDimension": "DIMENSION",
    "AcDbAlignedDimension": "DIMENSION",
    "AcDbRay": "RAY",
    "AcDbXline": "XLINE",
    "AcDbText": "TEXT",
}


def matches(entity, pairs):
    """What AutoCAD's selection filter does with these pairs, wildcards and all (case-insensitive)."""
    for code, value in pairs:
        if code == 0 and DXF.get(entity.ObjectName, "?") != value:
            return False
        if code == 8 and not fnmatch.fnmatch(entity.Layer.casefold(), str(value).casefold()):
            return False
        if code == 2 and not (entity.Name and fnmatch.fnmatch(entity.Name.casefold(), str(value).casefold())):
            return False
        if code == 62 and entity.Color != value:
            return False
    return True


class Selection(list):
    @property
    def Count(self):  # noqa: N802 - COM's name
        return len(self)

    def Item(self, i):  # noqa: N802
        return self[i]


class Doc:
    def __init__(self, entities):
        self.entities = entities

    def GetVariable(self, name):  # noqa: N802
        return {"INSUNITS": 4}[name]


class FakePlugin:
    """The plug-in's two reads, counted the way EntityTally.cs counts."""

    def __init__(self, doc):
        self.doc = doc
        self.calls: list[tuple[str, dict]] = []
        self.fail: Exception | None = None

    def __call__(self, operation, args):
        self.calls.append((operation, json.loads(json.dumps(args))))  # what goes over the pipe
        if self.fail:
            raise self.fail
        chosen = [e for e in self.doc.entities if matches(e, [tuple(p) for p in args["filter"]])]
        if operation == "count_entities":
            classes, layers = {}, {}
            for e in chosen:
                classes[e.ObjectName] = classes.get(e.ObjectName, 0) + 1
                layers[e.Layer] = layers.get(e.Layer, 0) + 1
            return {"total": len(chosen), "by_class": [[k, n] for k, n in classes.items()],
                    "by_layer": [[k, n] for k, n in layers.items()]}
        if operation == "entity_extents":
            boxes = [e.box for e in chosen if e.box is not None]
            if not boxes:
                return {"total": len(chosen), "measured": 0, "min": None, "max": None}
            return {"total": len(chosen), "measured": len(boxes),
                    "min": [min(b[0][i] for b in boxes) for i in range(3)],
                    "max": [max(b[1][i] for b in boxes) for i in range(3)]}
        raise AssertionError(operation)


DRAWING = [
    Entity("AcDbLine", "M-DUCT", ((0.0000006, 0.0, 0.0), (1000.0000004, 0.0, 0.0))),
    Entity("AcDbRotatedDimension", "A-DIMS", ((-50.25, -10.0, 0.0), (500.0, 40.0, 0.0))),
    Entity("AcDbLine", "M-DUCT", ((0.0, 200.0, 0.0), (1000.0, 200.0, 0.0))),
    Entity("AcDbAlignedDimension", "M-Duct-Notes", ((10.0, 10.0, 0.0), (20.0, 20.0, 0.0))),
    Entity("AcDbBlockReference", "M-DUCT", ((100.0, 50.0, -5.0), (150.0, 80.0, 30.0)), block="VAV-BOX", color=3),
    Entity("AcDbXline", "M-DUCT"),
    Entity("AcDbCircle", "E-LIGHT", ((5.0, 5.0, 0.0), (7.0, 7.0, 0.0)), color=2),
    Entity("AcDbRay", "CONSTRUCTION"),
    Entity("AcDbText", "E-LIGHT", ((1.0, 1.0, 0.0), (3.0, 2.0, 0.0))),
]


@pytest.fixture
def cad(monkeypatch):
    doc = Doc(list(DRAWING))
    plugin = FakePlugin(doc)

    async def run(fn):
        return fn()

    def select_filtered(doc_, entity_type=None, layer=None, block_name=None, color=None, **kw):
        doc_.com_selections = getattr(doc_, "com_selections", 0) + 1
        return Selection(e for e in doc_.entities if matches(e, filter_pairs(entity_type, layer, block_name, color)))

    monkeypatch.setattr(query, "run", run)
    monkeypatch.setattr(query, "get_doc", lambda: doc)
    monkeypatch.setattr(query, "select_filtered", select_filtered)
    monkeypatch.setattr(query, "discard_selection_set", lambda d, name=None: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: plugin)
    monkeypatch.setattr(_shared, "plugin_version", lambda: READS_SINCE)
    plugin.use = lambda on: monkeypatch.setattr(_shared, "plugin_runner", (lambda: plugin) if on else (lambda: None))
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
    asked = len(cad.calls)
    cad.use(False)
    by_com = answer(make())
    assert len(cad.calls) == asked
    return by_plugin, by_com


SUMMARIES = [
    {},
    {"layer": "M-*"},
    {"layer": "m-duct"},
    {"entity_type": "line"},
    {"entity_type": "dimension"},
    {"block_name": "VAV*"},
    {"color": "green"},
    {"color": 2},
    {"layer": "NOTHING-HERE"},
]


class TestSameAnswerEitherWay:
    @pytest.mark.parametrize("filters", SUMMARIES)
    def test_the_summary(self, cad, filters):
        by_plugin, by_com = both(cad, lambda: query.autocad_list_entities(summary_only=True, **filters))
        assert by_plugin == by_com

    def test_the_summary_counts_what_it_should(self, cad):
        out = json.loads(answer(query.autocad_list_entities(summary_only=True)))
        assert out["total_matching"] == len(DRAWING)
        # Two dimension classes are one type; the most common first, ties as first met.
        assert list(out["by_type"].items()) == [
            ("line", 2), ("dimension", 2), ("block", 1), ("xline", 1), ("circle", 1), ("ray", 1), ("text", 1)
        ]
        assert out["by_layer"] == {"M-DUCT": 4, "E-LIGHT": 2, "A-DIMS": 1, "M-Duct-Notes": 1, "CONSTRUCTION": 1}

    @pytest.mark.parametrize("layer", ["M-DUCT", "m-duct", "M-*", "E-LIGHT", "A-DIMS"])
    def test_the_extents_of_a_layer(self, cad, layer):
        by_plugin, by_com = both(cad, lambda: query.autocad_get_extents(layer=layer))
        assert by_plugin == by_com

    def test_the_box_is_rounded_as_com_rounds_it(self, cad):
        # Unrounded, the width would be 1000.0 here; COM rounds each corner first, and so does the plug-in path.
        query.get_doc().entities.append(Entity("AcDbLine", "ROUNDING", ((0.0000006, 0.0, 0.0), (1000.0000004, 0.0, 0.0))))
        by_plugin, by_com = both(cad, lambda: query.autocad_get_extents(layer="ROUNDING"))
        out = json.loads(by_plugin)
        assert by_plugin == by_com
        assert out["min"] == [0.000001, 0.0, 0.0] and out["max"] == [1000.0, 0.0, 0.0]
        assert out["width"] == 999.999999 and out["center"] == [500.0, 0.0] and out["entity_count"] == 1

    @pytest.mark.parametrize("layer", ["CONSTRUCTION", "NOTHING-HERE"])
    def test_a_layer_without_extents_is_the_same_error_either_way(self, cad, layer):
        cad.use(True)
        by_plugin = asyncio.run(query.autocad_get_extents(layer=layer))
        cad.use(False)
        by_com = asyncio.run(query.autocad_get_extents(layer=layer))
        assert by_plugin.startswith("Error") and by_plugin == by_com

    def test_only_rays_says_why_there_are_no_extents(self, cad):
        text = asyncio.run(query.autocad_get_extents(layer="CONSTRUCTION"))
        assert "none with extents" in text and "Infinity" not in text

    def test_an_empty_layer_says_check_the_name(self, cad):
        assert "autocad_list_layers" in asyncio.run(query.autocad_get_extents(layer="NOTHING-HERE"))


class TestWhatGoesToThePlugin:
    def test_the_filter_is_the_one_com_selects_with(self, cad):
        answer(query.autocad_list_entities(summary_only=True, block_name="VAV*", layer="M-*", color="green"))
        operation, args = cad.calls[-1]
        assert operation == "count_entities"
        assert args == {"filter": [[0, "INSERT"], [8, "M-*"], [2, "VAV*"], [62, 3]]}

    def test_no_filter_sends_an_empty_one(self, cad):
        answer(query.autocad_list_entities(summary_only=True))
        assert cad.calls[-1] == ("count_entities", {"filter": []})

    def test_extents_send_only_the_layer(self, cad):
        answer(query.autocad_get_extents(layer="E-*"))
        assert cad.calls[-1] == ("entity_extents", {"filter": [[8, "E-*"]]})

    def test_the_plugin_read_does_no_com_selection(self, cad):
        answer(query.autocad_list_entities(summary_only=True))
        answer(query.autocad_get_extents(layer="M-DUCT"))
        assert getattr(query.get_doc(), "com_selections", 0) == 0

    def test_a_full_listing_and_the_whole_drawing_stay_on_com(self, cad, monkeypatch):
        # Per-object detail and EXTMIN/EXTMAX gain nothing from the plug-in (yet): docs/13.
        monkeypatch.setattr(query, "describe", lambda e, include_geometry=True: {"type": short_type(e)})
        answer(query.autocad_list_entities(limit=3))
        assert cad.calls == []


class TestFallingBackToCom:
    def com_only(self, cad):
        return getattr(query.get_doc(), "com_selections", 0)

    def test_an_older_plugin_is_not_asked(self, cad, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_version", lambda: "1.7.0")
        out = json.loads(answer(query.autocad_list_entities(summary_only=True)))
        assert cad.calls == [] and self.com_only(cad) == 1 and out["total_matching"] == len(DRAWING)

    def test_an_unknown_version_is_asked(self, cad, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_version", lambda: None)
        answer(query.autocad_list_entities(summary_only=True))
        assert len(cad.calls) == 1 and self.com_only(cad) == 0

    @pytest.mark.parametrize(
        "refusal",
        [
            BridgeRefused(OLD_PLUGIN),
            BridgeRefused(
                "Heron in AutoCAD does not have the operation 'count_entities'. Update Heron so both sides "
                "match. Nothing was sent to AutoCAD."
            ),
            AutocadError("AutoCAD refused it (eInvalidInput). Nothing was changed."),
            AutocadError("Heron in AutoCAD hit an error: boom Nothing was changed."),
        ],
    )
    def test_a_plugin_that_cannot_read_it_hands_over_to_com(self, cad, refusal):
        cad.fail = refusal
        cad.use(True)
        by_fallback = answer(query.autocad_list_entities(summary_only=True))
        assert len(cad.calls) == 1 and self.com_only(cad) == 1
        cad.use(False)
        assert by_fallback == answer(query.autocad_list_entities(summary_only=True))

    @pytest.mark.parametrize(
        "refusal",
        [
            AutocadError(bridge.RUN_UNKNOWN.format(seconds=300, details="no answer")),
            BridgeRefused("The modeller pressed Stop in AutoCAD (HERONSTOP). Nothing was sent to AutoCAD."),
            BridgeRefused("Another chat is using AutoCAD through Heron right now. Nothing was sent to AutoCAD."),
        ],
    )
    def test_a_stop_or_no_answer_is_said_not_read_again_over_com(self, cad, refusal):
        cad.fail = refusal
        text = asyncio.run(query.autocad_list_entities(summary_only=True))
        assert text.startswith("Error") and self.com_only(cad) == 0

    def test_without_the_bridge_it_is_com(self, cad):
        cad.use(False)
        answer(query.autocad_get_extents(layer="M-DUCT"))
        assert cad.calls == [] and self.com_only(cad) == 1


class TestVersions:
    @pytest.mark.parametrize(
        ("version", "since", "expected"),
        [
            ("1.7.0", "1.8.0", True),
            ("1.2.9", "1.8.0", True),
            ("1.8.0", "1.8.0", False),
            ("1.10.0", "1.8.0", False),
            ("2.0", "1.8.0", False),
            ("1.8.0.0", "1.8.0", False),
            ("1.8.0-beta", "1.8.0", False),
            ("", "1.8.0", False),
            (None, "1.8.0", False),
            ("dev", "1.8.0", False),
        ],
    )
    def test_older(self, version, since, expected):
        assert older(version, since) is expected

    def test_the_reads_come_after_the_plugin_this_repository_shipped_without_them(self):
        props = (ROOT / "autocad" / "Directory.Build.props").read_text(encoding="utf-8")
        shipped = re.search(r"<Version>([\d.]+)</Version>", props).group(1)
        # Either the release that carries them is not out yet (1.7.0), or it is READS_SINCE or later.
        assert older("1.7.0", READS_SINCE) and (shipped == "1.7.0" or not older(shipped, READS_SINCE))

    def test_the_plugin_built_here_carries_the_reads_its_release_is_named_for(self):
        # D-155: the reads after 1.8.1 are named for plug-in 1.9.0, so the plug-in built here is 1.9.0 or later,
        # and 1.8.0 and 1.8.1 come before it (they are read over COM, as they always were).
        props = (ROOT / "autocad" / "Directory.Build.props").read_text(encoding="utf-8")
        built = re.search(r"<Version>([\d.]+)</Version>", props).group(1)
        assert READS_1_9_SINCE == "1.9.0" and not older(built, READS_1_9_SINCE)
        assert older("1.8.1", READS_1_9_SINCE) and older(READS_SINCE, READS_1_9_SINCE)
        assert not READS_1_9 & NEWER_READS

    def test_the_job_gives_the_plugin_version_from_its_address_file(self, monkeypatch):
        class FakeBridge:
            def find(self):
                return {"pipeName": "p", "token": "t", "addinVersion": "1.8.0"}

        job = gate.Job("autocad_list_entities", gate.Risk.READ, "List", "a.dwg", FakeBridge(), "j1", False, 0.0)
        monkeypatch.setattr(gate, "_current", job)
        assert gate.plugin_version() == "1.8.0"
        monkeypatch.setattr(gate, "_current", None)
        assert gate.plugin_version() is None


class TestOneFilterOneTypeName:
    @pytest.mark.parametrize(
        "args",
        [(None, None, None, None), ("circle", "A-*", None, None), (None, None, "DOOR", 1), ("block", " L1 ", " B ", 0)],
    )
    def test_com_and_the_plugin_get_the_same_filter(self, args):
        pairs = filter_pairs(*args)
        codes, values = build_filter(*args)
        if not pairs:
            assert codes is None and values is None
        else:
            assert [c for c, _ in pairs] == list(codes.value) and [v for _, v in pairs] == list(values.value)

    @pytest.mark.parametrize("name", [*OBJECT_NAME_MAP, "AcDbRotatedDimension", "AcDbArcDimension", "AcDbSurface", ""])
    def test_a_class_name_maps_as_an_object_does(self, name):
        class Obj:
            ObjectName = name

        assert short_type_name(name) == short_type(Obj())

    def test_every_type_alias_is_one_autocad_filters_on(self):
        assert all(value.isupper() for value in ENTITY_TYPE_ALIASES.values())


class TestBothSidesKnowTheReads:
    def test_the_plugin_lists_and_dispatches_both(self):
        listed = (ROOT / "autocad" / "Heron.AutoCAD.Bridge" / "PluginOperations.cs").read_text(encoding="utf-8")
        runner = (ROOT / "autocad" / "Heron.AutoCAD.Addin" / "PluginRunner.cs").read_text(encoding="utf-8")
        for name in OPERATIONS:
            assert f'["{name}"] = Risk.Read' in listed, name
            assert f'case "{name}":' in runner, name

    def test_the_server_asks_only_for_those(self):
        source = (ROOT / "src" / "autocad_mcp" / "tools" / "query.py").read_text(encoding="utf-8")
        assert set(re.findall(r'faster_read\("(\w+)"', source)) == set(OPERATIONS)


class TestDrawingReportCount:
    """autocad_drawing_report's model space count through count_entities (#193)."""

    class Items:
        def __init__(self, things):
            self.things = things

        @property
        def Count(self):  # noqa: N802
            return len(self.things)

        def Item(self, i):  # noqa: N802
            return self.things[i]

    class Doc:
        def __init__(self, names):
            self.ModelSpace = TestDrawingReportCount.Items([Entity(n, "0") for n in names])
            empty = TestDrawingReportCount.Items([])
            self.Layers = self.Blocks = self.TextStyles = self.DimStyles = self.Linetypes = self.Layouts = empty

        def GetVariable(self, name):  # noqa: N802
            return 4

    @pytest.fixture
    def report(self, monkeypatch):
        from autocad_mcp.tools import drawing_report

        state = {"calls": [], "echo": True}

        def plugin(operation, args):
            state["calls"].append((operation, dict(args)))
            assert operation == "count_entities" and args["space"] == "model"
            things, limit, classes = state["doc"].ModelSpace.things, args["limit"], {}
            for e in things[:limit]:
                classes[e.ObjectName] = classes.get(e.ObjectName, 0) + 1
            out = {"total": len(things), "by_class": [[k, n] for k, n in classes.items()], "by_layer": []}
            return {**out, "space": "model"} if state["echo"] else out

        async def run(fn):
            return fn()

        monkeypatch.setattr(drawing_report, "run", run)
        monkeypatch.setattr(drawing_report, "get_doc", lambda: state["doc"])
        monkeypatch.setattr(_shared, "plugin_version", lambda: READS_SINCE)

        def go(names, *, plugin_on=True):
            state["doc"] = self.Doc(names)
            monkeypatch.setattr(_shared, "plugin_runner", (lambda: plugin) if plugin_on else (lambda: None))
            return answer(drawing_report.autocad_drawing_report())

        go.state = state
        go.module = drawing_report
        return go

    NAMES = ["AcDbLine", "AcDbRotatedDimension", "AcDbLine", "AcDbMText", "AcDbAlignedDimension", "AcDbCircle"]

    def test_the_same_report_either_way(self, report):
        assert report(self.NAMES) == report(self.NAMES, plugin_on=False)
        assert report.state["calls"][0] == ("count_entities", {"filter": [], "space": "model", "limit": 50_000})

    def test_the_cut_off_is_the_same_either_way(self, report, monkeypatch):
        monkeypatch.setattr(report.module, "MOST_TO_COUNT", 3)
        by_plugin, by_com = report(self.NAMES), report(self.NAMES, plugin_on=False)
        assert by_plugin == by_com
        model = json.loads(by_plugin)["model_space"]
        assert model["total"] == 6 and model["by_type"] == {"line": 2, "dimension": 1}
        assert "first 3 of 6" in model["note"]

    def test_a_plugin_that_ignores_the_model_space_option_is_not_believed(self, report):
        # Built between #202 and #193, it would count the whole drawing; its answer lacks "space".
        report.state["echo"] = False
        out = json.loads(report(self.NAMES))
        assert len(report.state["calls"]) == 1 and out["model_space"]["total"] == 6
        assert out == json.loads(report(self.NAMES, plugin_on=False))
