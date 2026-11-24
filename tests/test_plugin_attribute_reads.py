"""Block attributes the plug-in reads in one go (#198, D-138), no AutoCAD.

autocad_extract_attributes, autocad_export_attribute_sheet and the reads of
autocad_set_attributes and autocad_apply_attribute_sheet look at every block
reference they select. COM does that 7-9 round trips per reference plus 2 per
attribute; Heron's plug-in does it in one go (block_attributes). The answer
must be the same either way, so each tool runs twice over one fake drawing,
once through a fake plug-in and once over fake COM, and the two answers are
compared as text. The writes stay COM's: after a plug-in read they land on the
COM objects, looked up by handle.

The fake plug-in writes rows the way EntityFacts.cs writes them, numbers as
Utf8JsonWriter does: a whole-number double goes over the pipe as 100, which
Python reads back as an int. EntityFactsTests.cs holds the C# side to that.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import math
import re
from pathlib import Path

import pytest

from autocad_mcp.acad import xlsx
from autocad_mcp.acad.selection import filter_pairs
from autocad_mcp.core import bridge
from autocad_mcp.core.bridge import OLD_PLUGIN, READS_1_9, READS_SINCE, BridgeRefused
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import _shared, attribute_sheet, standards, text_tools

ROOT = Path(__file__).resolve().parents[1]
OPERATION = "block_attributes"


class Att:
    """A COM attribute: TagString, TextString (writable), Invisible."""

    def __init__(self, tag, text, invisible=False):
        self.TagString, self.TextString, self.Invisible = tag, text, invisible


class Owner:
    def __init__(self, layout):
        self.IsLayout = layout is not None
        self.Layout = type("Layout", (), {"Name": layout})()


class Block:
    """One block reference of the fake drawing: what COM gives, and what the plug-in reads off the .NET object."""

    def __init__(self, handle, layer, name, effective, point, attributes, layout="Model", *,
                 constant=False, multiline=False, defines=None, com_has=None, net_effective=None,
                 owner_unreadable=False, plugin_attributes="read", plugin_point=None):
        self.handle, self.layer, self.name, self.effective = handle, layer, name, effective
        self.point, self.layout = point, layout
        self.attributes = [a if len(a) == 3 else (*a, False) for a in attributes]
        self.constant, self.multiline = constant, multiline
        self.defines = bool(attributes) if defines is None else defines
        self.com_has = bool(attributes) if com_has is None else com_has
        self.net_effective = effective or name if net_effective is None else net_effective
        self.owner_unreadable = owner_unreadable
        self.plugin_attributes = plugin_attributes
        self.plugin_point = point if plugin_point is None else plugin_point

    def com(self):
        atts = [Att(t, v, i) for t, v, i in self.attributes]
        return Com(self, atts)

    def row(self):
        """[handle, name, effective name, layer, point, layout, defines, attributes], as BlockAttributeFact writes it."""
        attributes = None
        if self.plugin_attributes == "read":
            attributes = [[t, v, i, self.constant, self.multiline] for t, v, i in self.attributes]
        layout = None if self.owner_unreadable else self.layout
        return [self.handle, self.name, self.net_effective, self.layer, list(self.plugin_point), layout,
                self.defines, attributes]


class Com:
    """A COM block reference: only what COM has."""

    def __init__(self, spec, atts):
        self.spec, self.atts = spec, atts
        self.Handle, self.Layer, self.Name = spec.handle, spec.layer, spec.name
        self.EffectiveName = spec.effective
        self.InsertionPoint = tuple(spec.point)
        self.HasAttributes = spec.com_has
        self.OwnerID = "unreadable" if spec.owner_unreadable else spec.layout
        self.updates = 0

    def GetAttributes(self):  # noqa: N802 - COM's name
        return tuple(self.atts)

    def Update(self):  # noqa: N802 - COM's name
        self.updates += 1


def drawing():
    return [
        # A changed dynamic block: COM's Name is the *U copy, EffectiveName the real one.
        Block("2A", "E-CCTV", "*U7", "CAMERA", (100.0, 200.0, 0.0), [("TAG", "CAM-01"), ("TYPE", "DOME", True)]),
        Block("2B", "E-CCTV", "CAMERA", "CAMERA", (1234.56789012, 5.5, 0.0), [("TAG", "CAM-02"), ("TYPE", "0050")]),
        Block("2C", "M-EQUIP", "DOOR", "DOOR", (1.0, 2.0, 0.0), []),  # no attributes: never listed
        Block("2D", "M-EQUIP", "VALVE", "VALVE", (3.0, 4.0, 0.0), [("TAG", "V-1"), ("SIZE", "DN50"), ("TAG", "V-2")]),
        Block("2E", "M-Equip", "Valve", "", (5.0, 6.0, 0.0), [("TAG", "V-3")]),  # COM's EffectiveName blank: its Name
        Block("3A", "A-TITLE", "TITLEBLOCK", "TITLEBLOCK", (0.0, 0.0, 0.0), [("REV", "A"), ("SHEET", "E-101")],
              layout="E-101"),
        Block("3B", "A-TITLE", "TITLEBLOCK", "TITLEBLOCK", (0.0, 0.0, 0.0), [("REV", "A"), ("SHEET", "E-102")],
              layout="E-102"),
        Block("3C", "A-TITLE", "TB", "TB", (-10.5, 0.0, 0.0), [("REV", "")], owner_unreadable=True),
    ]


def matches(spec, pairs):
    for code, value in pairs:
        if code == 0 and value != "INSERT":
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


class Doc:
    def __init__(self, path, objects):
        self.FullName = path
        self.objects = objects
        self.com_selections = 0
        self.looked_up: list[str] = []
        self.gone: set[str] = set()
        self.undo_marks = 0

    def GetVariable(self, name):  # noqa: N802 - COM's name
        assert name == "CMDACTIVE"
        return 0

    def ObjectIdToObject(self, owner):  # noqa: N802 - COM's name
        if owner == "unreadable":
            raise RuntimeError("no owner")
        return Owner(owner)

    def HandleToObject(self, handle):  # noqa: N802 - COM's name
        self.looked_up.append(handle)
        for ref in self.objects:
            if ref.Handle == handle and handle not in self.gone:
                return ref
        raise RuntimeError("no such handle")

    def StartUndoMark(self):  # noqa: N802 - COM's name
        self.undo_marks += 1

    def EndUndoMark(self):  # noqa: N802 - COM's name
        pass


class FakePlugin:
    """The plug-in's block_attributes, written the way EntityFacts.cs writes it."""

    def __init__(self, folder):
        self.folder = folder
        self.calls: list[tuple[str, dict]] = []
        self.fail: Exception | None = None
        self.specs = drawing()
        self.reset()

    def reset(self):
        """A fresh drawing from the specs: COM objects with their attributes as drawn."""
        self.doc = Doc(str(self.folder / "M-101.dwg"), [s.com() for s in self.specs])

    def values(self):
        return {ref.Handle: [(a.TagString, a.TextString) for a in ref.atts] for ref in self.doc.objects}

    def __call__(self, operation, args):
        self.calls.append((operation, json.loads(json.dumps(args))))  # what goes over the pipe
        if self.fail:
            raise self.fail
        if operation == "write_attributes":
            # As a plug-in from between D-138 and D-148: it reads, the writes go over COM
            # (test_plugin_attribute_writes.py has the plug-in's own write).
            raise BridgeRefused("Heron in AutoCAD does not have the operation 'write_attributes'. Update Heron so "
                                "both sides match. Nothing was sent to AutoCAD.")
        assert operation == OPERATION, operation
        # The plug-in reads the drawing as it is now (after any earlier write over COM).
        now = {ref.Handle: ref for ref in self.doc.objects}
        rows = []
        for spec in self.specs:
            if not matches(spec, [tuple(p) for p in args["filter"]]):
                continue
            row = spec.row()
            if row[7] is not None:
                row[7] = [[a.TagString, a.TextString, a.Invisible, spec.constant, spec.multiline]
                          for a in now[spec.handle].atts]
            rows.append(row)
        return json.loads(json.dumps(wire({"blocks": rows})))


@pytest.fixture
def cad(monkeypatch, tmp_path):
    plugin = FakePlugin(tmp_path)

    async def run(fn):
        return fn()

    def select_filtered(doc_, entity_type=None, layer=None, block_name=None, color=None, name=None):
        doc_.com_selections += 1
        pairs = filter_pairs(entity_type, layer, block_name, color)
        return [ref for ref in doc_.objects if matches(ref.spec, pairs)]

    for module in (text_tools, standards, attribute_sheet):
        monkeypatch.setattr(module, "run", run)
        monkeypatch.setattr(module, "get_doc", lambda: plugin.doc)
    for module in (text_tools, standards):
        monkeypatch.setattr(module, "select_filtered", select_filtered)
        monkeypatch.setattr(module, "iter_selection", lambda sel: iter(list(sel)))
        monkeypatch.setattr(module, "discard_selection_set", lambda d, name=None: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: plugin)
    monkeypatch.setattr(_shared, "plugin_version", lambda: READS_SINCE)
    plugin.use = lambda on: monkeypatch.setattr(_shared, "plugin_runner", (lambda: plugin) if on else (lambda: None))
    return plugin


def answer(coro) -> str:
    text = asyncio.run(coro)
    assert not text.startswith("Error"), text
    return text


def both(cad, make) -> tuple[str, str]:
    """The tool's answer through the plug-in, then over COM, each on a fresh drawing, as text."""
    cad.reset()
    cad.use(True)
    by_plugin = answer(make())
    assert cad.calls, "the plug-in was not asked"
    assert cad.doc.com_selections == 0, "the plug-in path read over COM as well"
    after_plugin, asked = cad.values(), len(cad.calls)
    cad.reset()
    cad.use(False)
    by_com = answer(make())
    assert len(cad.calls) == asked
    assert cad.doc.com_selections > 0
    assert cad.values() == after_plugin, "the drawing was left differently"
    return by_plugin, by_com


def fell_back(cad, make) -> None:
    """The plug-in was asked, its answer not used: the tool read over COM, with COM's own answer."""
    cad.reset()
    cad.use(True)
    by_fallback = answer(make())
    assert cad.calls and cad.doc.com_selections > 0
    cad.reset()
    cad.use(False)
    assert by_fallback == answer(make())


def ids(options):
    return ",".join(f"{k}={v}" for k, v in options.items()) or "default"


# ---- autocad_extract_attributes ------------------------------------------------

EXTRACTS = [
    {"output": output, **extra}
    for output in ("json", "csv")
    for extra in ({}, {"block_name": "camera"}, {"block_name": "VALVE"}, {"block_name": "TitleBlock"},
                  {"layer": "M-*"}, {"layer": "e-cctv"}, {"block_name": "DOOR"}, {"layer": "NOTHING-HERE"})
]


class TestExtractTheSameEitherWay:
    @pytest.mark.parametrize("options", EXTRACTS, ids=ids)
    def test_extract_attributes(self, cad, options):
        by_plugin, by_com = both(cad, lambda: standards.autocad_extract_attributes(**options))
        assert by_plugin == by_com

    def test_what_it_lists_is_what_com_lists(self, cad):
        rows = json.loads(answer(standards.autocad_extract_attributes()))["rows"]
        # The door has no attributes; the dynamic block goes by its real name; the duplicate tag keeps the last value.
        assert [r["handle"] for r in rows] == ["2A", "2B", "2D", "2E", "3A", "3B", "3C"]
        assert rows[0]["block"] == "CAMERA" and rows[0]["insertion"] == [100.0, 200.0, 0.0]
        assert rows[0]["attributes"] == {"TAG": "CAM-01", "TYPE": "DOME"}  # the invisible one too
        assert rows[2]["attributes"] == {"TAG": "V-2", "SIZE": "DN50"} and rows[3]["block"] == "Valve"
        assert all(isinstance(v, float) for row in rows for v in row["insertion"])


# ---- autocad_export_attribute_sheet --------------------------------------------

def exported(cad, options):
    """The export's answer and the workbook it wrote, read back; the file is then removed so the next is named the same."""
    out = json.loads(answer(attribute_sheet.autocad_export_attribute_sheet(**options)))
    path = Path(out["saved"])
    sheets = xlsx.read(path.read_bytes())
    path.unlink()
    return out, sheets


class TestExportTheSameEitherWay:
    @pytest.mark.parametrize("options", [{}, {"block_name": "titleblock"}, {"layer": "E-*"}, {"block_name": "Valve"}],
                             ids=ids)
    def test_export_attribute_sheet(self, cad, options):
        cad.use(True)
        by_plugin = exported(cad, options)
        assert cad.calls and cad.doc.com_selections == 0
        cad.use(False)
        by_com = exported(cad, options)
        assert cad.doc.com_selections == 1
        assert by_plugin == by_com

    def test_the_sheet_holds_each_block_on_its_layout(self, cad):
        _, sheets = exported(cad, {})
        rows = {row[0]: row for row in sheets["Attributes"][1:]}
        assert rows["2A"][1:3] == ["CAMERA", "Model"] and rows["3A"][1:3] == ["TITLEBLOCK", "E-101"]
        assert rows["3B"][2] == "E-102" and rows["3C"][2] == ""  # an owner that cannot be read: no layout

    def test_nothing_to_export_is_said_the_same_way(self, cad):
        cad.use(True)
        by_plugin = asyncio.run(attribute_sheet.autocad_export_attribute_sheet(block_name="DOOR"))
        cad.use(False)
        assert by_plugin == asyncio.run(attribute_sheet.autocad_export_attribute_sheet(block_name="DOOR"))
        assert "No block with attributes matches" in by_plugin


# ---- autocad_set_attributes ------------------------------------------------------

SETS = [
    {"values": {"REV": "B"}},
    {"values": {"REV": "B"}, "block_name": "titleblock"},
    {"values": {"rev": "A"}, "block_name": "TITLEBLOCK"},  # nothing differs: no write
    {"values": {"TAG": "X-1", "NOPE": "1"}, "layer": "M-*"},
    {"rows": [{"SHEET": "E-102", "REV": "C"}, {"SHEET": "E-999", "REV": "D"}], "key": "SHEET"},
    {"rows": [{"layout": "E-101", "REV": "C"}, {"layout": "Model", "TYPE": "PTZ"}], "key": "layout"},
]


class TestSetAttributesTheSameEitherWay:
    @pytest.mark.parametrize("dry_run", [True, False], ids=["dry_run", "write"])
    @pytest.mark.parametrize("options", SETS, ids=[str(i) for i in range(len(SETS))])
    def test_set_attributes(self, cad, options, dry_run):
        by_plugin, by_com = both(cad, lambda: text_tools.autocad_set_attributes(**options, dry_run=dry_run))
        assert by_plugin == by_com

    def test_a_dry_run_looks_up_no_block_over_com(self, cad):
        answer(text_tools.autocad_set_attributes(values={"REV": "B"}, dry_run=True))
        assert cad.doc.looked_up == [] and cad.doc.com_selections == 0 and cad.doc.undo_marks == 0

    def test_the_write_lands_on_the_com_objects_looked_up_by_handle(self, cad):
        out = json.loads(answer(text_tools.autocad_set_attributes(values={"REV": "B"}, block_name="TITLEBLOCK")))
        assert out["changed"] == 2 and cad.doc.undo_marks == 1
        # Each changed block looked up once, nothing else; the write itself is over COM, as before.
        assert sorted(set(cad.doc.looked_up)) == ["3A", "3B"] and len(cad.doc.looked_up) == 2
        values = cad.values()
        assert values["3A"] == [("REV", "B"), ("SHEET", "E-101")] and values["3C"] == [("REV", "")]
        assert {ref.Handle: ref.updates for ref in cad.doc.objects if ref.updates} == {"3A": 1, "3B": 1}


# ---- autocad_apply_attribute_sheet ------------------------------------------------

def edited_sheet(cad, name="edited.xlsx"):
    """The export, edited by the modeller: 2A's TAG and 3B's REV, written next to the drawing."""
    cad.use(False)
    cad.reset()
    out, sheets = exported(cad, {})
    rows = sheets["Attributes"]
    heading = rows[0]
    for row in rows[1:]:
        if row[0] == "2A":
            row[heading.index("TAG")] = "CAM-11"
        if row[0] == "3B":
            row[heading.index("REV")] = "B"
        if row[0] == "2E":
            row[heading.index("TAG")] = "V-33"
    book = xlsx.write([("Attributes", rows, None), ("As exported", sheets["As exported"], None)])
    (cad.folder / name).write_bytes(book)
    assert out["blocks"] == 7
    return name


class TestApplySheetTheSameEitherWay:
    @pytest.mark.parametrize("dry_run", [True, False], ids=["dry_run", "write"])
    def test_apply_attribute_sheet(self, cad, dry_run):
        name = edited_sheet(cad)
        by_plugin, by_com = both(cad, lambda: attribute_sheet.autocad_apply_attribute_sheet(path=name, dry_run=dry_run))
        assert by_plugin == by_com
        out = json.loads(by_plugin)
        assert (out["would_change"] if dry_run else out["changed"]) == 3

    def test_the_writes_land_on_the_com_objects(self, cad):
        name = edited_sheet(cad)
        cad.reset()
        cad.use(True)
        out = json.loads(answer(attribute_sheet.autocad_apply_attribute_sheet(path=name)))
        assert out["changed"] == 3 and out["failed"] == [] and cad.doc.undo_marks == 1
        assert sorted(cad.doc.looked_up) == ["2A", "2E", "3B"]
        values = cad.values()
        assert values["2A"][0] == ("TAG", "CAM-11") and values["3B"][0] == ("REV", "B")

    def test_a_block_gone_before_the_write_is_listed_as_failed_not_a_crash(self, cad):
        name = edited_sheet(cad)
        cad.reset()
        cad.use(True)
        # Erased between the plug-in's read and the write: its handle no longer resolves over COM.
        cad.doc.gone.add("2A")
        out = json.loads(answer(attribute_sheet.autocad_apply_attribute_sheet(path=name)))
        assert out["changed"] == 2 and [f["handle"] for f in out["failed"]] == ["2A"]
        assert cad.values()["2A"][0] == ("TAG", "CAM-01")

    def test_set_attributes_on_a_block_gone_before_the_write_says_so(self, cad):
        cad.doc.gone.add("3A")
        out = asyncio.run(text_tools.autocad_set_attributes(values={"REV": "B"}, block_name="TITLEBLOCK"))
        assert out.startswith("Error") and "No entity with handle '3A'" in out


# ---- what is sent, and falling back to COM ----------------------------------------

TOOLS = [
    lambda: standards.autocad_extract_attributes(),
    lambda: text_tools.autocad_set_attributes(values={"REV": "B"}),
    lambda: text_tools.autocad_set_attributes(values={"REV": "B"}, dry_run=True),
]
TOOL_IDS = ["extract", "set", "set_dry_run"]


class TestWhatIsSent:
    def test_the_insert_filter_with_the_layer(self, cad):
        answer(standards.autocad_extract_attributes(layer=" E-* ", block_name="CAMERA"))
        # The block name is matched by the server, as over COM: never sent.
        assert cad.calls[-1] == (OPERATION, {"filter": [[0, "INSERT"], [8, "E-*"]]})

    def test_without_a_layer_every_block_reference(self, cad):
        answer(attribute_sheet.autocad_export_attribute_sheet())
        assert cad.calls[-1] == (OPERATION, {"filter": [[0, "INSERT"]]})


class TestFallsBackToCom:
    @pytest.mark.parametrize(
        "refusal",
        [
            BridgeRefused(OLD_PLUGIN),
            # Plug-ins 1.8.0 and 1.8.1, and one built before this read, pass READS_SINCE but have no block_attributes.
            BridgeRefused(
                "Heron in AutoCAD does not have the operation 'block_attributes'. Update Heron so both sides "
                "match. Nothing was sent to AutoCAD."
            ),
            AutocadError("AutoCAD refused it (eInvalidInput). Nothing was changed."),
        ],
    )
    @pytest.mark.parametrize("make", TOOLS, ids=TOOL_IDS)
    def test_a_plugin_that_cannot_read_it_hands_over_to_com(self, cad, refusal, make):
        cad.fail = refusal
        fell_back(cad, make)
        assert len(cad.calls) == 1

    @pytest.mark.parametrize("make", TOOLS, ids=TOOL_IDS)
    def test_an_older_plugin_is_not_asked(self, cad, monkeypatch, make):
        monkeypatch.setattr(_shared, "plugin_version", lambda: "1.7.0")
        answer(make())
        assert cad.calls == [] and cad.doc.com_selections == 1

    @pytest.mark.parametrize("flag", ["multiline", "constant"])
    @pytest.mark.parametrize("make", TOOLS, ids=TOOL_IDS)
    def test_a_multiline_or_constant_attribute_sends_the_read_to_com(self, cad, flag, make):
        cad.specs = [*drawing(), Block("4A", "E-CCTV", "NOTE", "NOTE", (0.0, 0.0, 0.0), [("REV", "line one")],
                                       **{flag: True})]
        fell_back(cad, make)

    @pytest.mark.parametrize(
        "odd",
        [
            # A block whose definition has attribute definitions (constant ones, say) but no attributes on it.
            {"defines": True, "attributes": [], "com_has": True},
            {"defines": True, "attributes": [], "com_has": False},
            # Attributes on the reference that its definition no longer defines.
            {"defines": False, "attributes": [("REV", "Z")], "com_has": False},
            {"defines": False, "attributes": [("REV", "Z")], "com_has": True},
        ],
        ids=["defined-none-on-it-com-yes", "defined-none-on-it-com-no", "on-it-not-defined-com-no",
             "on-it-not-defined-com-yes"],
    )
    @pytest.mark.parametrize("make", TOOLS, ids=TOOL_IDS)
    def test_attributes_the_definition_does_not_match_send_the_read_to_com(self, cad, odd, make):
        odd = dict(odd)
        attributes = odd.pop("attributes")
        cad.specs = [*drawing(), Block("4B", "A-TITLE", "TITLEBLOCK", "TITLEBLOCK", (0.0, 0.0, 0.0), attributes, **odd)]
        fell_back(cad, make)

    def test_an_unsure_block_the_tool_does_not_read_leaves_the_plugin_answer_standing(self, cad):
        cad.specs = [*drawing(), Block("4A", "E-CCTV", "NOTE", "NOTE", (0.0, 0.0, 0.0), [("REV", "x")], multiline=True),
                     Block("4B", "A-TITLE", "STAMP", "STAMP", (0.0, 0.0, 0.0), [], defines=True)]
        for options in ({"block_name": "TitleBlock"}, {"block_name": "camera", "output": "csv"}):
            by_plugin, by_com = both(cad, lambda options=options: standards.autocad_extract_attributes(**options))
            assert by_plugin == by_com
        by_plugin, by_com = both(cad, lambda: text_tools.autocad_set_attributes(values={"REV": "Q"}, block_name="TITLEBLOCK"))
        assert by_plugin == by_com
        # Asked about NOTE itself, the read goes to COM.
        fell_back(cad, lambda: standards.autocad_extract_attributes(block_name="note"))

    @pytest.mark.parametrize(
        "change",
        [
            {"net_effective": None},  # the plug-in could not read the real name
            {"plugin_attributes": "failed"},  # nor every attribute
            {"plugin_point": (math.inf, 0.0, 0.0)},  # a number Utf8JsonWriter refuses
        ],
        ids=["no-real-name", "attributes-failed", "not-finite"],
    )
    @pytest.mark.parametrize("make", TOOLS, ids=TOOL_IDS)
    def test_what_the_plugin_could_not_read_sends_the_read_to_com(self, cad, change, make):
        block = Block("4C", "E-CCTV", "CAMERA", "CAMERA", (7.0, 8.0, 0.0), [("TAG", "CAM-03")])
        for key, value in change.items():
            setattr(block, key, value)
        cad.specs = [*drawing(), block]
        fell_back(cad, make)

    @pytest.mark.parametrize("reply", [
        {}, {"blocks": "none"}, {"blocks": [["2A", "CAMERA"]]},
        # A row of entity_texts' shape: not this read's.
        {"blocks": [["2A", "E-CCTV", None, [0, 0, 0], "CAMERA", [["TAG", "X", False, False]]]]},
        {"blocks": [["2A", "CAMERA", "CAMERA", "0", [0, 0], "Model", True, [["TAG", "X", False, False, False]]]]},
        {"blocks": [["2A", "CAMERA", "CAMERA", "0", [0, 0, 0], 5, True, [["TAG", "X", False, False, False]]]]},
        {"blocks": [["2A", "CAMERA", "CAMERA", "0", [0, 0, 0], "Model", "yes", [["TAG", "X", False, False, False]]]]},
        {"blocks": [["2A", "CAMERA", "CAMERA", "0", [0, 0, 0], "Model", True, [["TAG", "X", False, False]]]]},
        {"blocks": [["2A", "CAMERA", "CAMERA", "0", [0, 0, 0], "Model", True, [["TAG", 5, False, False, False]]]]},
        {"blocks": [["2A", "CAMERA", "CAMERA", "0", [0, 0, 0], "Model", True, [["TAG", "X", 0, False, False]]]]},
        {"blocks": [["2A", "CAMERA", "CAMERA", "0", [0, True, 0], "Model", True, [["TAG", "X", False, False, False]]]]},
    ])
    @pytest.mark.parametrize("make", TOOLS, ids=TOOL_IDS)
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
    @pytest.mark.parametrize("make", TOOLS, ids=TOOL_IDS)
    def test_a_stop_or_no_answer_is_said_not_read_again_over_com(self, cad, refusal, make):
        cad.fail = refusal
        assert asyncio.run(make()).startswith("Error")
        assert cad.doc.com_selections == 0 and cad.doc.undo_marks == 0

    def test_a_sheet_falls_back_too(self, cad):
        name = edited_sheet(cad)
        cad.fail = BridgeRefused(OLD_PLUGIN)
        fell_back(cad, lambda: attribute_sheet.autocad_apply_attribute_sheet(path=name, dry_run=True))
        cad.fail = None
        cad.specs = [*drawing(), Block("4A", "E-CCTV", "NOTE", "NOTE", (0.0, 0.0, 0.0), [("REV", "x")], constant=True)]
        cad.reset()
        cad.use(True)
        by_fallback = exported(cad, {"block_name": "NOTE"})
        assert cad.calls[-1][0] == OPERATION and cad.doc.com_selections == 1
        cad.use(False)
        assert by_fallback == exported(cad, {"block_name": "NOTE"})


class TestThroughTheRealGate:
    """A Read inside a Change job: the gate's answer line, Keep or Discard and the plug-in calls stay the same."""

    @pytest.fixture
    def gated(self, cad, monkeypatch):
        import test_gate

        env = test_gate.env.__wrapped__(monkeypatch)  # the gate with the bridge and COM faked
        test_gate.FakeBridge.ask_to_keep = True
        runs: list[str] = []

        def run(self, job, operation, args, timeout=None):
            runs.append(operation)
            if cad.answers:
                return cad(operation, args)
            raise BridgeRefused(
                f"Heron in AutoCAD does not have the operation '{operation}'. Update Heron so both sides match. "
                "Nothing was sent to AutoCAD."
            )

        monkeypatch.setattr(test_gate.FakeBridge, "run", run, raising=False)
        monkeypatch.setattr(_shared, "plugin_runner", __import__("autocad_mcp.core.gate", fromlist=["gate"]).plugin_runner)
        monkeypatch.setattr(_shared, "plugin_version", lambda: None)  # not known: the plug-in is asked
        cad.runs, cad.bridge, cad.env = runs, test_gate.FakeBridge, env
        return cad

    @pytest.mark.parametrize("options", [
        {"values": {"REV": "B"}},
        {"values": {"rev": "A"}, "block_name": "TITLEBLOCK"},  # nothing differs
        {"values": {"REV": "B"}, "dry_run": True},
    ], ids=["write", "no-change", "dry_run"])
    def test_set_attributes_answers_the_same_with_or_without_the_read(self, gated, options):
        writes = not options.get("dry_run") and options["values"] != {"rev": "A"}
        # What the plug-in counts for the job: the read itself adds nothing to it.
        gated.bridge.counted = {"added": 0, "modified": 7 if writes else 0, "erased": 0}
        found = {}
        for answers in (True, False):
            gated.reset()
            gated.answers = answers
            gated.bridge.calls = []
            gated.runs.clear()
            text = asyncio.run(text_tools.autocad_set_attributes(**options))
            # After a plug-in read, the write is offered to it too (D-148); this one has none, so COM writes.
            assert gated.runs == [OPERATION] + (["write_attributes"] if writes and answers else [])
            assert (gated.doc.com_selections == 0) == answers
            found[answers] = (text, list(gated.bridge.calls), gated.values(), gated.doc.undo_marks)
        assert found[True] == found[False]
        text, calls, _, marks = found[True]
        first = text.splitlines()[0]
        assert calls[0][:3] == ("begin", "autocad_set_attributes", "change") and calls[-1][0] == "end"
        if not writes:
            # The read wrote nothing: no undo step, no Keep or Discard question, nothing "unknown".
            assert marks == 0 and not first.startswith("OUTCOME UNKNOWN"), first
            assert not any(c[0] == "ask_keep" for c in calls)
        else:
            assert first.startswith("DONE - ") and marks == 1, first
            assert any(c[0] == "ask_keep" for c in calls)


class TestBothSidesKnowTheRead:
    def test_the_plugin_lists_and_dispatches_it(self):
        listed = (ROOT / "autocad" / "Heron.AutoCAD.Bridge" / "PluginOperations.cs").read_text(encoding="utf-8")
        runner = (ROOT / "autocad" / "Heron.AutoCAD.Addin" / "PluginRunner.cs").read_text(encoding="utf-8")
        assert f'["{OPERATION}"] = Risk.Read' in listed
        assert f'case "{OPERATION}":' in runner

    def test_the_server_asks_for_it_and_names_it_newer(self):
        source = (ROOT / "src" / "autocad_mcp" / "tools" / "text_tools.py").read_text(encoding="utf-8")
        assert OPERATION in set(re.findall(r'faster_read\("(\w+)"', source))
        assert OPERATION in READS_1_9
