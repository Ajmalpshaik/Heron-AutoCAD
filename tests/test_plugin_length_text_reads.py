"""Lengths and texts the plug-in reads in one go (#195, #197, D-134), no AutoCAD.

autocad_total_length, autocad_measure(layer=...), autocad_count_text and
autocad_find_text look at every object they select. COM does that a round
trip per property; Heron's plug-in does it in one go. The answer must be the
same either way, so each tool runs twice over one fake drawing, once through a
fake plug-in and once over fake COM, and the two answers are compared as text.

The fake COM objects have only the properties COM has (an ellipse has no
Closed, a 3D polyline no Area, a circle no Length), as AutoCAD's own type
libraries list them. The fake plug-in over-supplies as the .NET objects do (an
ellipse is Closed, a 3D polyline has an Area) and writes numbers as
Utf8JsonWriter does: a whole-number double goes over the pipe as 3000, which
Python reads back as an int. EntityFactsTests.cs holds the C# side to that.
"""

from __future__ import annotations

import asyncio
import fnmatch
import itertools
import json
import math
import re
from pathlib import Path

import pytest

from autocad_mcp.acad.selection import filter_pairs
from autocad_mcp.core import bridge
from autocad_mcp.core.bridge import NEWER_READS, OLD_PLUGIN, READS_SINCE, BridgeRefused
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import _shared, query, takeoff, text_tools

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ("entity_lengths", "entity_texts")
_handles = itertools.count(0x2A0)


class Com:
    """A fake COM object: only the properties given exist; one given as an exception raises it."""

    def __init__(self, props):
        self.__dict__["_props"] = props

    def __getattr__(self, name):
        props = self.__dict__["_props"]
        if name not in props:
            raise AttributeError(name)
        value = props[name]
        if isinstance(value, Exception):
            raise value
        return value


DXF = {
    "AcDbLine": "LINE", "AcDbPolyline": "LWPOLYLINE", "AcDb2dPolyline": "POLYLINE", "AcDb3dPolyline": "POLYLINE",
    "AcDbArc": "ARC", "AcDbCircle": "CIRCLE", "AcDbEllipse": "ELLIPSE", "AcDbSpline": "SPLINE",
    "AcDbHatch": "HATCH", "AcDbRegion": "REGION", "AcDbText": "TEXT", "AcDbMText": "MTEXT",
    "AcDbBlockReference": "INSERT", "AcDbPoint": "POINT", "AcDbRotatedDimension": "DIMENSION",
    "AcDbRay": "RAY", "AcDbSweptSurface": "SURFACE",
}


class Spec:
    """One object of the fake drawing: what COM gives, and what the plug-in reads off the .NET object."""

    def __init__(self, cls, layer, com, lengths, texts=None):
        self.cls, self.layer = cls, layer
        self.handle = f"{next(_handles):X}"
        self.com = Com({"ObjectName": cls, "Layer": layer, "Handle": self.handle, **com})
        self.lengths = lengths  # [length, area, closed, shape], as EntityReads.CurveFacts reads them
        self.texts = texts  # [text, point, name, attributes], as EntityReads.Texts reads them


def line(layer, length):
    return Spec("AcDbLine", layer, {"Length": length}, [length, 0.0, False, None])


def lwpoly(layer, length, area, closed, cls="AcDbPolyline"):
    return Spec(cls, layer, {"Length": length, "Area": area, "Closed": closed}, [length, area, closed, None])


def poly3d(layer, length, closed, net_area):
    # COM's 3D polyline has no Area; .NET's Curve.Area gives one.
    return Spec("AcDb3dPolyline", layer, {"Length": length, "Closed": closed}, [length, net_area, closed, None])


def arc(layer, radius, sweep):
    length, area = radius * sweep, radius * radius * (sweep - math.sin(sweep)) / 2
    return Spec("AcDbArc", layer, {"ArcLength": length, "Area": area}, [length, area, False, None])


def circle(layer, radius):
    length, area = 2 * math.pi * radius, math.pi * radius * radius
    return Spec("AcDbCircle", layer, {"Circumference": length, "Area": area}, [length, area, True, None])


def ellipse(layer, major, minor, start, end, area):
    com = {"Area": area, "MajorRadius": major, "MinorRadius": minor, "StartParameter": start, "EndParameter": end}
    full = math.isclose(end - start, 2 * math.pi)
    return Spec("AcDbEllipse", layer, com, [None, area, full, ["ellipse", major, minor, start, end]])


def spline(layer, degree, points, knots, weights, closed, area):
    rational = bool(weights)
    com = {"Area": area, "Closed": closed, "Degree": degree, "IsRational": rational,
           "ControlPoints": tuple(points), "Knots": tuple(knots)}
    if rational:
        com["Weights"] = tuple(weights)
    return Spec("AcDbSpline", layer, com,
                [None, area, closed, ["spline", degree, rational, list(points), list(knots), list(weights)]])


def other(cls, layer, com=None, lengths=None):
    return Spec(cls, layer, com or {}, lengths or [None, None, None, None])


def text(layer, value, point, cls="AcDbText"):
    return Spec(cls, layer, {"TextString": value, "InsertionPoint": point}, [None, None, None, None],
                [value, list(point), None, None])


def block(layer, name, effective, attributes, point, flags=(False, False)):
    attrs = tuple(Com({"TagString": t, "TextString": v}) for t, v in attributes)
    com = {"Name": name, "EffectiveName": effective, "InsertionPoint": point, "HasAttributes": bool(attributes),
           "GetAttributes": lambda: attrs}
    return Spec("AcDbBlockReference", layer, com, [None, None, None, None],
                [None, list(point), name, [[t, v, *flags] for t, v in attributes]])


CURVE = [1.0, 2.0, 0.0, 400.0, 900.0, 0.0, 1300.0, -200.0, 0.0, 2000.0, 500.0, 0.0]
ROUND = [0.0, 0.0, 0.0, 500.0, 0.0, 0.0, 500.0, 500.0, 0.0]

NO_LENGTH = Spec("AcDbLine", "M-PIPE", {"Length": RuntimeError("no length")}, [None, 0.0, False, None])
NO_DEFINITION = Spec(
    "AcDbSpline", "M-PIPE",
    {"Area": 10.0, "Closed": False, "ControlPoints": RuntimeError("no points"), "Degree": 3, "IsRational": False,
     "Knots": (0.0,)},
    [None, 10.0, False, None],
)

DRAWING = [
    line("M-PIPE", 3000.0),  # a whole-number length: 3000 on the wire
    line("M-PIPE", 1234.5678901234567),
    lwpoly("M-PIPE", 2500.25, 1000.0, False),  # open: COM gives it an area, total_length does not count it
    lwpoly("M-DUCT", 4000.0, 1000000.0, True),
    lwpoly("M-Duct", 400.0, 10000.0, True, cls="AcDb2dPolyline"),
    poly3d("M-PIPE", 900.0, True, 5000.0),  # closed, but COM has no Area for it
    poly3d("M-PIPE", 300.0, False, 0.0),
    arc("M-PIPE", 100.0, math.pi / 2),
    circle("M-PIPE", 50.0),
    ellipse("M-HVAC", 100.0, 50.0, 0.0, 2 * math.pi, 15707.963267948966),  # full, yet COM has no Closed
    ellipse("M-HVAC", 100.0, 50.0, 0.5, 2.0, 2000.0),
    spline("M-PIPE", 3, CURVE, [0, 0, 0, 0, 1, 1, 1, 1], [], False, 123.0),
    spline("M-HVAC", 2, ROUND, [0, 0, 0, 1, 1, 1], [1.0, 0.7071067811865476, 1.0], True, 456.0),
    NO_LENGTH,
    NO_DEFINITION,
    other("AcDbHatch", "M-PIPE", {"Area": 5000.0}, [None, 5000.0, None, None]),
    other("AcDbRegion", "M-HVAC", {"Area": 250.0}, [None, 250.0, None, None]),
    other("AcDbPoint", "M-HVAC"),
    other("AcDbRotatedDimension", "M-DUCT"),
    other("AcDbRay", "M-PIPE", lengths=[None, None, False, None]),
    text("A-ANNO", "DN50", (100.0, 200.0, 0.0)),
    text("M-PIPE", "dn50 ", (1234.56789012, 5.5, 0.0)),
    text("M-PIPE", "FFL +3.150", (10.0, 20.0, 0.0)),
    text("A-ANNO", "{\\fArial|b1;ROOM 12}\\PFFL 0.00", (300.0, 400.0, 0.0), cls="AcDbMText"),
    text("M-PIPE", "\\A1;DN100", (0.0, 0.0, 0.0), cls="AcDbMText"),
    block("M-EQUIP", "*U7", "VALVE", [("SIZE", "DN50"), ("TAG", "V-101")], (50.0, 60.0, 0.0)),
    block("M-EQUIP", "DOOR", "DOOR", [("NO", "D-101"), ("FFL", "FFL 0.00")], (70.0, 80.0, 0.0)),
    block("A-ANNO", "ROOM", "ROOM", [], (90.0, 95.0, 0.0)),
    block("M-EQUIP", "VALVE", "VALVE", [("size", "DN80"), ("TAG", "V-102")], (1.5, 2.5, 0.0)),
]


def matches(spec, pairs):
    for code, value in pairs:
        if code == 0 and DXF.get(spec.cls) != value:
            return False
        if code == 8 and not fnmatch.fnmatch(spec.layer.casefold(), str(value).casefold()):
            return False
    return True


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


class FakePlugin:
    """The plug-in's two reads, written the way EntityFacts.cs writes them."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.fail: Exception | None = None
        self.drawing = list(DRAWING)
        self.groups_short = False

    def __call__(self, operation, args):
        self.calls.append((operation, json.loads(json.dumps(args))))  # what goes over the pipe
        if self.fail:
            raise self.fail
        if operation == "entity_lengths":
            chosen = [s for s in self.drawing if matches(s, [tuple(p) for p in args["filter"]])]
            if args.get("classes"):
                chosen = [s for s in chosen if s.cls in args["classes"]]
            out = {"items": [[s.cls, s.layer, *s.lengths] for s in chosen]}
        elif operation == "entity_texts":
            groups = []
            for pairs in args["filters"]:
                chosen = [s for s in self.drawing if matches(s, [tuple(p) for p in pairs])]
                groups.append([[s.handle, s.layer, *(s.texts or [None, None, None, None])] for s in chosen])
            out = {"groups": groups[:-1] if self.groups_short else groups}
        else:
            raise AssertionError(operation)
        return json.loads(json.dumps(wire(out)))


class Doc:
    def __init__(self):
        self.com_selections = 0

    def GetVariable(self, name):  # noqa: N802 - COM's name
        assert name == "INSUNITS"
        return 4


@pytest.fixture
def cad(monkeypatch):
    plugin = FakePlugin()
    doc = Doc()

    async def run(fn):
        return fn()

    def select_filtered(doc_, entity_type=None, layer=None, block_name=None, color=None, name=None):
        doc_.com_selections += 1
        pairs = filter_pairs(entity_type, layer, block_name, color)
        return [s.com for s in plugin.drawing if matches(s, pairs)]

    for module in (takeoff, query, text_tools):
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
    text_ = asyncio.run(coro)
    assert not text_.startswith("Error"), text_
    return text_


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
    assert cad.doc.com_selections > 0
    return by_plugin, by_com


def fell_back(cad, make) -> None:
    """The plug-in was asked, its answer not used: the tool read over COM, with COM's own answer."""
    cad.use(True)
    by_fallback = answer(make())
    assert cad.calls and cad.doc.com_selections > 0
    cad.use(False)
    assert by_fallback == answer(make())


def ids(options):
    return ",".join(f"{k}={v}" for k, v in options.items()) or "default"


# ---- autocad_total_length ------------------------------------------------------

TOTALS = [
    {"group_by": group_by, **extra}
    for group_by in ("layer", "type", "none")
    for extra in ({}, {"layer": "M-*"}, {"layer": "m-hvac"}, {"entity_type": "polyline"}, {"entity_type": "spline"},
                  {"entity_type": "ellipse", "layer": "M-HVAC"}, {"layer": "NOTHING-HERE"})
]


class TestTotalLengthTheSameEitherWay:
    @pytest.mark.parametrize("options", TOTALS, ids=ids)
    def test_total_length(self, cad, options):
        by_plugin, by_com = both(cad, lambda: takeoff.autocad_total_length(**options))
        assert by_plugin == by_com

    def test_what_it_counts_is_what_com_counts(self, cad):
        rows = {r["type"]: r for r in json.loads(answer(takeoff.autocad_total_length(group_by="type")))["rows"]}
        # No area for a full ellipse (COM gives it no Closed) or a closed 3D polyline (no Area);
        # the open polyline's area is left out; the circle's and the closed ones' are in.
        assert rows["AcDbEllipse"]["area"] == 0.0 and rows["AcDb3dPolyline"]["area"] == 0.0
        assert rows["AcDbPolyline"]["area"] == 1000000.0
        assert rows["AcDbCircle"]["area"] == pytest.approx(math.pi * 2500)
        assert rows["AcDbSpline"]["area"] == 456.0
        # A spline and an ellipse are measured from their definitions; a failed read is unmeasured.
        assert rows["AcDbSpline"]["unmeasured"] == 1 and rows["AcDbSpline"]["count"] == 3
        assert rows["AcDbLine"]["unmeasured"] == 1 and rows["AcDbLine"]["length"] == 3000.0 + 1234.5678901234567
        assert "AcDbHatch" not in rows and "AcDbText" not in rows and "AcDbRay" not in rows

    def test_lengths_come_to_the_last_digit(self, cad):
        by_plugin, by_com = both(cad, lambda: takeoff.autocad_total_length(group_by="none"))
        assert json.loads(by_plugin)["total_length"] == json.loads(by_com)["total_length"]
        assert repr(json.loads(by_plugin)["total_length"]) == repr(json.loads(by_com)["total_length"])


class TestWhatTotalLengthSends:
    def test_the_filter_and_only_the_curves(self, cad):
        answer(takeoff.autocad_total_length(entity_type="polyline", layer=" M-* "))
        assert cad.calls[-1] == ("entity_lengths", {
            "filter": [[0, "LWPOLYLINE"], [8, "M-*"]],
            "classes": sorted(takeoff._CURVES),
        })


# ---- autocad_measure(layer=...) ------------------------------------------------

class TestMeasureTheSameEitherWay:
    @pytest.mark.parametrize("layer", ["M-PIPE", "m-pipe", "M-*", "M-HVAC", "M-DUCT", "A-ANNO", "M-EQUIP"])
    def test_measure(self, cad, layer):
        by_plugin, by_com = both(cad, lambda: query.autocad_measure(layer=layer))
        assert by_plugin == by_com

    def test_what_it_counts_is_what_com_counts(self, cad):
        out = json.loads(answer(query.autocad_measure(layer="M-HVAC")))
        # Ellipses, a region and a spline have an area but no Length or ArcLength; the point has neither.
        assert out["entity_count"] == 5 and out["counted_length"] == 0 and out["counted_area"] == 4
        out = json.loads(answer(query.autocad_measure(layer="M-PIPE")))
        # A circle's Circumference is not a Length; the open polyline, the arc and the hatch have an area.
        lengths = 3000.0 + 1234.5678901234567 + 2500.25 + 900.0 + 300.0 + 100.0 * math.pi / 2
        assert out["total_length"] == round(lengths, 6)
        assert out["by_type"]["line"] == 3 and out["by_type"]["text"] == 2

    def test_an_empty_layer_is_said_the_same_way(self, cad):
        cad.use(True)
        by_plugin = asyncio.run(query.autocad_measure(layer="NOTHING-HERE"))
        cad.use(False)
        assert by_plugin == asyncio.run(query.autocad_measure(layer="NOTHING-HERE"))
        assert "has no entities" in by_plugin

    def test_it_sends_the_layer_filter_and_asks_for_every_class(self, cad):
        answer(query.autocad_measure(layer=" M-PIPE "))
        assert cad.calls[-1] == ("entity_lengths", {"filter": [[8, "M-PIPE"]]})

    def test_handles_are_still_read_over_com(self, cad, monkeypatch):
        monkeypatch.setattr(query, "resolve_handle", lambda doc, h: DRAWING[0].com)
        answer(query.autocad_measure(handles=["2A0"]))
        assert cad.calls == []


# ---- falling back to COM -------------------------------------------------------

LENGTH_TOOLS = [
    lambda: takeoff.autocad_total_length(group_by="type"),
    lambda: query.autocad_measure(layer="M-*"),
]


class TestLengthsFallBackToCom:
    @pytest.mark.parametrize(
        "refusal",
        [
            BridgeRefused(OLD_PLUGIN),
            # Plug-ins 1.8.0 and 1.8.1 pass READS_SINCE but have no entity_lengths.
            BridgeRefused(
                "Heron in AutoCAD does not have the operation 'entity_lengths'. Update Heron so both sides "
                "match. Nothing was sent to AutoCAD."
            ),
            AutocadError("AutoCAD refused it (eInvalidInput). Nothing was changed."),
        ],
    )
    @pytest.mark.parametrize("make", LENGTH_TOOLS, ids=["total_length", "measure"])
    def test_a_plugin_that_cannot_read_it_hands_over_to_com(self, cad, refusal, make):
        cad.fail = refusal
        fell_back(cad, make)
        assert len(cad.calls) == 1

    @pytest.mark.parametrize("make", LENGTH_TOOLS, ids=["total_length", "measure"])
    def test_an_older_plugin_is_not_asked(self, cad, monkeypatch, make):
        monkeypatch.setattr(_shared, "plugin_version", lambda: "1.7.0")
        answer(make())
        assert cad.calls == [] and cad.doc.com_selections == 1

    def test_a_class_com_reads_differently_is_read_over_com(self, cad):
        # A swept surface has a COM Length that the plug-in does not read.
        cad.drawing = [*DRAWING, other("AcDbSweptSurface", "M-PIPE", {"Length": 10.0})]
        fell_back(cad, lambda: query.autocad_measure(layer="M-PIPE"))
        # Two lines, the open polyline, two 3D polylines, the arc and the surface (a line's length failed).
        assert json.loads(answer(query.autocad_measure(layer="M-PIPE")))["counted_length"] == 7

    def test_a_helix_with_a_spline_definition_still_reads_as_com(self, cad):
        # .NET's Helix is a Spline; COM's helix has only TotalLength. The plug-in's answer stands.
        definition = ["spline", 3, False, CURVE, [0, 0, 0, 0, 1, 1, 1, 1], []]
        cad.drawing = [*DRAWING, other("AcDbHelix", "M-COIL", {"TotalLength": 50.0}, [None, 3.0, False, definition])]
        by_plugin, by_com = both(cad, lambda: query.autocad_measure(layer="M-COIL"))
        assert by_plugin == by_com
        assert json.loads(by_plugin)["counted_length"] == 0 and json.loads(by_plugin)["counted_area"] == 0

    def test_a_number_that_is_not_finite_is_read_over_com(self, cad):
        cad.drawing = [*DRAWING, line("M-PIPE", math.inf)]
        cad.use(True)
        answer(takeoff.autocad_total_length())
        assert cad.doc.com_selections == 1

    @pytest.mark.parametrize("reply", [
        {}, {"items": "none"}, {"items": [["AcDbLine", "0", 1.0]]}, {"items": ["AcDbLine0123"]},
        {"items": [["AcDbLine", "0", True, None, None, None]]},
        {"items": [["AcDbPolyline", "0", 1.0, 1.0, None, None]]},  # no Closed flag
        {"items": [["AcDbEllipse", "0", None, 1.0, None, ["spline", 3, False, [], [], []]]]},
        {"items": [["AcDbSpline", "0", None, 1.0, False, ["spline", 3.0, False, [], [], []]]]},
    ])
    @pytest.mark.parametrize("make", LENGTH_TOOLS, ids=["total_length", "measure"])
    def test_an_answer_of_the_wrong_shape_is_read_over_com(self, cad, reply, monkeypatch, make):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: lambda operation, args: reply)
        answer(make())
        assert cad.doc.com_selections == 1

    @pytest.mark.parametrize(
        "refusal",
        [
            AutocadError(bridge.RUN_UNKNOWN.format(seconds=300, details="no answer")),
            BridgeRefused("The modeller pressed Stop in AutoCAD (HERONSTOP). Nothing was sent to AutoCAD."),
        ],
    )
    @pytest.mark.parametrize("make", LENGTH_TOOLS, ids=["total_length", "measure"])
    def test_a_stop_or_no_answer_is_said_not_read_again_over_com(self, cad, refusal, make):
        cad.fail = refusal
        assert asyncio.run(make()).startswith("Error")
        assert cad.doc.com_selections == 0


class TestTheTableIsCOMs:
    def test_every_class_total_length_measures_is_in_it(self):
        assert takeoff._CURVES <= set(takeoff.COM_FACTS)

    def test_it_matches_autocads_own_type_library(self):
        # Read off the .tlb file only (AutoCAD is not started); skipped where AutoCAD is not installed (CI).
        pythoncom = pytest.importorskip("pythoncom")
        libraries = sorted(Path(r"C:\Program Files\Common Files\Autodesk Shared").glob("axdb2[456]enu.tlb"))
        if not libraries:
            pytest.skip("no AutoCAD type library on this PC")
        interfaces = {
            "AcDbLine": "IAcadLine", "AcDbPolyline": "IAcadLWPolyline", "AcDb2dPolyline": "IAcadPolyline",
            "AcDb3dPolyline": "IAcad3DPolyline", "AcDbArc": "IAcadArc", "AcDbCircle": "IAcadCircle",
            "AcDbEllipse": "IAcadEllipse", "AcDbSpline": "IAcadSpline", "AcDbHatch": "IAcadHatch",
            "AcDbRegion": "IAcadRegion", "AcDbText": "IAcadText", "AcDbMText": "IAcadMText",
            "AcDbBlockReference": "IAcadBlockReference", "AcDbMInsertBlock": "IAcadMInsertBlock",
            "AcDbPoint": "IAcadPoint", "AcDbLeader": "IAcadLeader", "AcDbMLeader": "IAcadMLeader",
            "AcDbHelix": "IAcadHelix", "AcDbRotatedDimension": "IAcadDimRotated", "AcDbTable": "IAcadTable",
            "AcDb3dSolid": "IAcad3DSolid", "AcDbRay": "IAcadRay", "AcDbXline": "IAcadXline",
        }
        for path in libraries:
            lib = pythoncom.LoadTypeLib(str(path))
            props: dict[str, set[str]] = {}
            for i in range(lib.GetTypeInfoCount()):
                info, found, todo = lib.GetTypeInfo(i), set(), [lib.GetTypeInfo(i)]
                while todo:
                    ti = todo.pop()
                    attr = ti.GetTypeAttr()
                    found.update(ti.GetNames(ti.GetFuncDesc(f).memid)[0] for f in range(attr.cFuncs))
                    for k in range(attr.cImplTypes):
                        try:
                            todo.append(ti.GetRefTypeInfo(ti.GetRefTypeOfImplType(k)))
                        except Exception:  # noqa: BLE001 - IDispatch's own base
                            continue
                props[lib.GetDocumentation(i)[0]] = found
                del info
            for cls, interface in interfaces.items():
                have = props[interface]
                length, area, closed = takeoff.COM_FACTS[cls]
                lengths = {"Length", "ArcLength", "Circumference"} & have
                assert lengths == ({length} if length else set()), (path.name, cls)
                assert ("Area" in have) == area, (path.name, cls)
                assert ("Closed" in have) == closed, (path.name, cls)


# ---- autocad_count_text and autocad_find_text -----------------------------------

COUNTS = [
    {"source": source, **extra}
    for source in ("all", "text", "attributes")
    for extra in ({}, {"tag": "size"}, {"layer": "M-*"}, {"pattern": "^DN"}, {"normalise": False},
                  {"sum_numeric": True}, {"layer": "NOTHING-HERE"})
]

FINDS = [
    {"query": q, **extra}
    for q in ("dn50", "FFL", "101", "room", "zzz")
    for extra in ({}, {"include_attributes": False}, {"limit": 1}, {"limit": 2})
]


class TestCountTextTheSameEitherWay:
    @pytest.mark.parametrize("options", COUNTS, ids=ids)
    def test_count_text(self, cad, options):
        by_plugin, by_com = both(cad, lambda: text_tools.autocad_count_text(**options))
        assert by_plugin == by_com

    def test_formatting_codes_come_as_com_leaves_them(self, cad):
        counts = json.loads(answer(text_tools.autocad_count_text(source="text", normalise=False)))["counts"]
        assert "{\\fArial|b1;ROOM 12}\\PFFL 0.00" in counts and "\\A1;DN100" in counts


class TestFindTextTheSameEitherWay:
    @pytest.mark.parametrize("options", FINDS, ids=ids)
    def test_find_text(self, cad, options):
        by_plugin, by_com = both(cad, lambda: query.autocad_find_text(**options))
        assert by_plugin == by_com

    def test_what_it_finds_is_what_com_finds(self, cad):
        found = json.loads(answer(query.autocad_find_text(query="room")))["matches"]
        assert found[0]["text"] == "{\\fArial|b1;ROOM 12}\\PFFL 0.00" and found[0]["position"] == [300.0, 400.0, 0.0]
        valve = json.loads(answer(query.autocad_find_text(query="v-101")))["matches"]
        # The block's own Name, the *U one of a changed dynamic block, as COM gives it.
        assert valve == [{"handle": DRAWING[-4].handle, "type": "block", "layer": "M-EQUIP", "text": "V-101",
                          "position": [50.0, 60.0, 0.0], "source": "attribute", "attribute_tag": "TAG",
                          "block_name": "*U7"}]


class TestWhatTheTextToolsSend:
    def test_count_text_sends_one_filter_per_kind_in_order(self, cad):
        answer(text_tools.autocad_count_text(layer=" M-* "))
        assert cad.calls[-1] == ("entity_texts", {"filters": [
            [[0, "TEXT"], [8, "M-*"]], [[0, "MTEXT"], [8, "M-*"]], [[0, "INSERT"], [8, "M-*"]],
        ]})

    def test_find_text_without_attributes_asks_for_no_blocks(self, cad):
        answer(query.autocad_find_text(query="x", include_attributes=False))
        assert cad.calls[-1] == ("entity_texts", {"filters": [[[0, "TEXT"]], [[0, "MTEXT"]]]})


TEXT_TOOLS = [
    lambda: text_tools.autocad_count_text(sum_numeric=True),
    lambda: query.autocad_find_text(query="d", limit=3),
]


class TestTextsFallBackToCom:
    @pytest.mark.parametrize(
        "refusal",
        [
            BridgeRefused(OLD_PLUGIN),
            BridgeRefused(
                "Heron in AutoCAD does not have the operation 'entity_texts'. Update Heron so both sides "
                "match. Nothing was sent to AutoCAD."
            ),
            AutocadError("Heron in AutoCAD hit an error: boom Nothing was changed."),
        ],
    )
    @pytest.mark.parametrize("make", TEXT_TOOLS, ids=["count_text", "find_text"])
    def test_a_plugin_that_cannot_read_it_hands_over_to_com(self, cad, refusal, make):
        cad.fail = refusal
        fell_back(cad, make)
        assert len(cad.calls) == 1

    @pytest.mark.parametrize("make", TEXT_TOOLS, ids=["count_text", "find_text"])
    def test_an_older_plugin_is_not_asked(self, cad, monkeypatch, make):
        monkeypatch.setattr(_shared, "plugin_version", lambda: "1.7.0")
        answer(make())
        assert cad.calls == [] and cad.doc.com_selections == 3

    @pytest.mark.parametrize("flags", [(True, False), (False, True)], ids=["multiline", "constant"])
    @pytest.mark.parametrize("make", TEXT_TOOLS, ids=["count_text", "find_text"])
    def test_a_multiline_or_constant_attribute_is_read_over_com(self, cad, flags, make):
        cad.drawing = [*DRAWING, block("M-EQUIP", "NOTE", "NOTE", [("TEXT", "DN25 line one")], (0.0, 0.0, 0.0), flags)]
        fell_back(cad, make)

    @pytest.mark.parametrize("make", TEXT_TOOLS, ids=["count_text", "find_text"])
    def test_an_answer_without_every_group_is_read_over_com(self, cad, make):
        cad.groups_short = True
        fell_back(cad, make)

    @pytest.mark.parametrize("reply", [
        {}, {"groups": "none"}, {"groups": [[]]},
        {"groups": [[["1", "0", "A", [0, 0], None, None]], [], []]},  # a 2D point
        {"groups": [[["1", "0", None, [0, 0, 0], None, None]], [], []]},  # a text without its text
        {"groups": [[], [], [["1", "0", None, [0, 0, 0], None, [["T", "V", False, False]]]]]},  # a block without its name
        {"groups": [[], [], [["1", "0", None, [0, 0, 0], "B", [["T", 5, False, False]]]]]},
        {"groups": [[["1", "0", "A", [0, "not finite", 0], None, None]], [], []]},
    ])
    def test_an_answer_of_the_wrong_shape_is_read_over_com(self, cad, reply, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: lambda operation, args: reply)
        answer(text_tools.autocad_count_text())
        assert cad.doc.com_selections == 3

    @pytest.mark.parametrize("make", TEXT_TOOLS, ids=["count_text", "find_text"])
    def test_a_stop_is_said_not_read_again_over_com(self, cad, make):
        cad.fail = BridgeRefused("The modeller pressed Stop in AutoCAD (HERONSTOP). Nothing was sent to AutoCAD.")
        assert asyncio.run(make()).startswith("Error")
        assert cad.doc.com_selections == 0


class TestBothSidesKnowTheReads:
    def test_the_plugin_lists_and_dispatches_both(self):
        listed = (ROOT / "autocad" / "Heron.AutoCAD.Bridge" / "PluginOperations.cs").read_text(encoding="utf-8")
        runner = (ROOT / "autocad" / "Heron.AutoCAD.Addin" / "PluginRunner.cs").read_text(encoding="utf-8")
        for name in OPERATIONS:
            assert f'["{name}"] = Risk.Read' in listed, name
            assert f'case "{name}":' in runner, name

    def test_the_server_asks_for_both_and_names_them_newer(self):
        asked = set()
        for module in ("takeoff.py", "query.py", "text_tools.py"):
            source = (ROOT / "src" / "autocad_mcp" / "tools" / module).read_text(encoding="utf-8")
            asked |= set(re.findall(r'faster_read\("(\w+)"', source))
        assert set(OPERATIONS) <= asked and set(OPERATIONS) <= NEWER_READS
