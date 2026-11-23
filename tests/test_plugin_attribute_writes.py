"""Attribute writes made by the plug-in in one transaction (#200, D-148), no AutoCAD.

autocad_set_attributes and autocad_apply_attribute_sheet wrote each changed
cell over COM: 3 round trips plus one per attribute, and a failure half way
left a half-written sheet. After the plug-in has read the blocks (D-138) it now
writes every planned cell in one transaction (write_attributes): all of them,
or none. Only the cells the server planned are sent (D-69). Each tool runs
twice over one fake drawing (test_plugin_attribute_reads.py's), once with a
plug-in that writes and once over COM, and the answers and the attributes left
are compared.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
import test_plugin_attribute_reads as reads

from autocad_mcp.core import bridge
from autocad_mcp.core.bridge import OLD_PLUGIN, READS_SINCE, BridgeRefused
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import _shared, attribute_sheet, standards, text_tools

ROOT = Path(__file__).resolve().parents[1]
WRITE = "write_attributes"
USE_COM = "Heron writes these over COM instead."


class WritingPlugin(reads.FakePlugin):
    """test_plugin_attribute_reads' plug-in, with write_attributes as AttributeWrites.cs makes it."""

    def __init__(self, folder):
        super().__init__(folder)
        self.write_fail: Exception | None = None
        self.report = None  # replaces the write's answer when set
        self.locked: set[str] = set()  # blocks whose attributes AutoCAD will not take
        self.fields: set[str] = set()  # blocks whose attributes hold a field

    def __call__(self, operation, args):
        if operation != WRITE:
            return super().__call__(operation, args)
        self.calls.append((operation, json.loads(json.dumps(args))))
        if self.write_fail:
            raise self.write_fail
        before = self.values()
        try:
            written = self.write(args["changes"])
        except AutocadError:
            # The transaction is aborted: every attribute as it was.
            for ref in self.doc.objects:
                for att, (_, text) in zip(ref.atts, before[ref.Handle], strict=True):
                    att.TextString = text
            raise
        report = {"written": len(args["changes"]), "attributes": written}
        return report if self.report is None else self.report(report)

    def write(self, changes):
        by_handle = {ref.Handle: ref for ref in self.doc.objects if ref.Handle not in self.doc.gone}
        count = 0
        for handle, tag, text in changes:
            ref = by_handle.get(handle)
            if ref is None:
                raise AutocadError(f"Block {handle} is not in the drawing any more, so nothing was written. Look at "
                                   "the drawing and ask again. Nothing was changed.")
            hit = False
            for att in ref.atts:
                if att.TagString != tag:
                    continue
                if handle in self.fields:
                    raise AutocadError(f"{tag} on block {handle} is a field. {USE_COM} Nothing was changed.")
                if handle in self.locked:
                    raise AutocadError(f"Block {handle} would not take {tag} (eOnLockedLayer), so nothing was "
                                       "written: no attribute changed. Nothing was changed.")
                att.TextString = text
                hit = True
                count += 1
            if not hit:
                raise AutocadError(f"Block {handle} no longer has the tag {tag}, so nothing was written. Nothing was "
                                   "changed.")
        return count


@pytest.fixture
def cad(monkeypatch, tmp_path):
    plugin = WritingPlugin(tmp_path)

    async def run(fn):
        return fn()

    def select_filtered(doc_, entity_type=None, layer=None, block_name=None, color=None, name=None):
        doc_.com_selections += 1
        pairs = reads.filter_pairs(entity_type, layer, block_name, color)
        return [ref for ref in doc_.objects if reads.matches(ref.spec, pairs)]

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


answer = reads.answer


def com_writes(cad) -> int:
    return len(cad.doc.looked_up) + sum(ref.updates for ref in cad.doc.objects)


def both(cad, make, prepare=lambda: None):
    """The tool through the writing plug-in, then over COM, each on a fresh drawing: (answer, attributes left) each."""
    cad.reset()
    prepare()
    cad.use(True)
    by_plugin = answer(make())
    assert com_writes(cad) == 0 and cad.doc.com_selections == 0, "the plug-in path used COM as well"
    plugin_left = cad.values()
    cad.reset()
    prepare()
    cad.use(False)
    by_com = answer(make())
    return (by_plugin, plugin_left), (by_com, cad.values())


SETS = [s for s in reads.SETS if s.get("values") != {"rev": "A"}] + [
    {"values": {"TAG": "V-9"}, "block_name": "valve"},  # the tag twice on one block: both set, as over COM
]


class TestSetAttributesTheSameEitherWay:
    @pytest.mark.parametrize("options", SETS, ids=[str(i) for i in range(len(SETS))])
    def test_set_attributes(self, cad, options):
        by_plugin, by_com = both(cad, lambda: text_tools.autocad_set_attributes(**options))
        assert by_plugin == by_com

    def test_the_write_is_one_call_with_only_the_planned_cells(self, cad):
        out = json.loads(answer(text_tools.autocad_set_attributes(values={"REV": "B"}, block_name="TITLEBLOCK")))
        assert out["changed"] == 2 and cad.doc.undo_marks == 1
        assert cad.calls[-1] == (WRITE, {"changes": [["3A", "REV", "B"], ["3B", "REV", "B"]]})
        assert [c[0] for c in cad.calls] == [reads.OPERATION, WRITE]

    def test_the_tag_twice_on_one_block_sets_both(self, cad):
        answer(text_tools.autocad_set_attributes(values={"TAG": "V-9"}, block_name="valve"))
        assert cad.values()["2D"] == [("TAG", "V-9"), ("SIZE", "DN50"), ("TAG", "V-9")]

    def test_nothing_to_change_asks_no_write(self, cad):
        answer(text_tools.autocad_set_attributes(values={"rev": "A"}, block_name="TITLEBLOCK"))
        assert [c[0] for c in cad.calls] == [reads.OPERATION] and cad.doc.undo_marks == 0

    def test_a_dry_run_asks_no_write(self, cad):
        answer(text_tools.autocad_set_attributes(values={"REV": "B"}, dry_run=True))
        assert [c[0] for c in cad.calls] == [reads.OPERATION]


class TestApplySheetTheSameEitherWay:
    def test_apply_attribute_sheet(self, cad):
        name = reads.edited_sheet(cad)
        (plugin_text, plugin_left), (com_text, com_left) = both(
            cad, lambda: attribute_sheet.autocad_apply_attribute_sheet(path=name))
        assert (plugin_text, plugin_left) == (com_text, com_left)
        out = json.loads(plugin_text)
        assert out["changed"] == 3 and out["failed"] == []

    def test_only_the_cells_the_modeller_changed_are_sent(self, cad):
        name = reads.edited_sheet(cad)
        cad.reset()
        cad.use(True)
        answer(attribute_sheet.autocad_apply_attribute_sheet(path=name))
        assert cad.calls[-1] == (WRITE, {"changes": [["2A", "TAG", "CAM-11"], ["2E", "TAG", "V-33"], ["3B", "REV", "B"]]})


class TestAllOrNone:
    def test_a_block_that_will_not_take_a_cell_refuses_the_whole_sheet(self, cad):
        name = reads.edited_sheet(cad)
        cad.reset()
        cad.use(True)
        cad.locked.add("3B")  # the last of the three cells
        before = cad.values()
        text = asyncio.run(attribute_sheet.autocad_apply_attribute_sheet(path=name))
        assert text.startswith("Error") and "would not take REV" in text and "Nothing was changed" in text
        assert cad.values() == before and com_writes(cad) == 0

    def test_a_block_gone_before_the_write_refuses_set_attributes_with_nothing_written(self, cad):
        cad.doc.gone.add("3B")
        before = cad.values()
        text = asyncio.run(text_tools.autocad_set_attributes(values={"REV": "B"}, block_name="TITLEBLOCK"))
        assert text.startswith("Error") and "Block 3B is not in the drawing any more" in text
        assert cad.values() == before and com_writes(cad) == 0

    def test_over_com_the_same_sheet_is_half_written_which_is_what_the_plugin_takes_away(self, cad):
        name = reads.edited_sheet(cad)
        cad.reset()
        cad.use(True)
        cad.doc.gone.add("3B")
        cad.write_fail = BridgeRefused("Heron in AutoCAD does not have the operation 'write_attributes'. Nothing was "
                                       "sent to AutoCAD.")
        out = json.loads(answer(attribute_sheet.autocad_apply_attribute_sheet(path=name)))
        assert out["changed"] == 2 and [f["handle"] for f in out["failed"]] == ["3B"]


class TestFallsBackToCom:
    @pytest.mark.parametrize("refusal", [
        BridgeRefused(OLD_PLUGIN),
        BridgeRefused("Heron in AutoCAD does not have the operation 'write_attributes'. Update Heron so both sides "
                      "match. Nothing was sent to AutoCAD."),
        AutocadError(f"REV on block 3A is a field. {USE_COM} Nothing was changed."),
    ], ids=["old", "no-operation", "not-trusted"])
    def test_a_plugin_that_will_not_write_them_hands_over_to_com(self, cad, refusal):
        cad.write_fail = refusal
        make = lambda: text_tools.autocad_set_attributes(values={"REV": "B"})  # noqa: E731
        cad.reset()
        cad.use(True)
        text = answer(make())
        assert [c[0] for c in cad.calls][-1] == WRITE and com_writes(cad) > 0
        left = cad.values()
        cad.write_fail = None
        _, by_com = both(cad, make)
        assert (text, left) == by_com

    def test_a_field_the_plugin_will_not_write_is_written_over_com(self, cad):
        make = lambda: text_tools.autocad_set_attributes(values={"REV": "C"})  # noqa: E731
        cad.reset()
        cad.fields.add("3B")
        cad.use(True)
        plugin_text = answer(make())
        plugin_left = cad.values()
        assert com_writes(cad) > 0  # nothing written by the plug-in, every cell over COM
        cad.fields.clear()
        _, by_com = both(cad, make)
        assert (plugin_text, plugin_left) == by_com

    def test_a_read_over_com_writes_over_com_too(self, cad):
        cad.specs = [*reads.drawing(), reads.Block("4A", "E-CCTV", "NOTE", "NOTE", (0.0, 0.0, 0.0), [("REV", "x")],
                                                   multiline=True)]
        cad.reset()
        answer(text_tools.autocad_set_attributes(values={"REV": "B"}))
        assert [c[0] for c in cad.calls] == [reads.OPERATION] and cad.doc.com_selections == 1 and com_writes(cad) > 0

    def test_an_older_plugin_is_not_asked(self, cad, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_version", lambda: "1.7.0")
        answer(text_tools.autocad_set_attributes(values={"REV": "B"}))
        assert cad.calls == []

    @pytest.mark.parametrize("refusal", [
        AutocadError(bridge.RUN_UNKNOWN.format(seconds=300, details="no answer")),
        BridgeRefused("The modeller pressed Stop in AutoCAD (HERONSTOP). Nothing was sent to AutoCAD."),
    ])
    def test_a_stop_or_no_answer_is_said_never_written_again_over_com(self, cad, refusal):
        cad.write_fail = refusal
        assert asyncio.run(text_tools.autocad_set_attributes(values={"REV": "B"})).startswith("Error")
        assert com_writes(cad) == 0

    def test_an_answer_that_does_not_count_every_cell_is_outcome_unknown(self, cad):
        cad.report = lambda report: {**report, "written": report["written"] - 1}
        text = asyncio.run(text_tools.autocad_set_attributes(values={"REV": "B"}))
        assert text.startswith("Error") and "Outcome unknown" in text and com_writes(cad) == 0


class TestThroughTheRealGate:
    """The writes inside their Change job: the answer line, Keep or Discard and the undo mark, the same either way."""

    @pytest.fixture
    def gated(self, cad, monkeypatch):
        import test_gate

        test_gate.env.__wrapped__(monkeypatch)
        test_gate.FakeBridge.ask_to_keep = True

        def run(self, job, operation, args, timeout=None):
            return cad(operation, args)

        monkeypatch.setattr(test_gate.FakeBridge, "run", run, raising=False)
        monkeypatch.setattr(_shared, "plugin_runner", __import__("autocad_mcp.core.gate", fromlist=["gate"]).plugin_runner)
        monkeypatch.setattr(_shared, "plugin_version", lambda: None)
        cad.bridge = test_gate.FakeBridge
        return cad

    @pytest.mark.parametrize("make", [
        lambda: text_tools.autocad_set_attributes(values={"REV": "B"}),
        lambda: text_tools.autocad_set_attributes(values={"REV": "Q"}, block_name="TITLEBLOCK"),
    ], ids=["all", "title-blocks"])
    def test_keep_or_discard_asks_about_the_same_writes_either_way(self, gated, make):
        gated.bridge.counted = {"added": 0, "modified": 4, "erased": 0}
        found = {}
        for writes in (True, False):
            gated.reset()
            gated.bridge.calls = []
            gated.write_fail = None if writes else BridgeRefused(
                "Heron in AutoCAD does not have the operation 'write_attributes'. Nothing was sent to AutoCAD.")
            text = asyncio.run(make())
            assert (com_writes(gated) == 0) == writes
            found[writes] = (text, [c[:3] for c in gated.bridge.calls], gated.values(), gated.doc.undo_marks)
        assert found[True] == found[False]
        text, calls, _, marks = found[True]
        assert text.splitlines()[0].startswith("DONE - ") and marks == 1
        assert calls[0][:3] == ("begin", "autocad_set_attributes", "change")
        assert any(c[0] == "ask_keep" for c in calls)


class TestBothSidesKnowTheWrite:
    def test_the_plugin_lists_and_dispatches_it(self):
        listed = (ROOT / "autocad" / "Heron.AutoCAD.Bridge" / "PluginOperations.cs").read_text(encoding="utf-8")
        runner = (ROOT / "autocad" / "Heron.AutoCAD.Addin" / "PluginRunner.cs").read_text(encoding="utf-8")
        assert f'["{WRITE}"] = Risk.Change' in listed and f'case "{WRITE}":' in runner

    def test_the_server_asks_for_it_and_knows_the_plugins_words(self):
        source = (ROOT / "src" / "autocad_mcp" / "tools" / "text_tools.py").read_text(encoding="utf-8")
        assert WRITE in set(re.findall(r'faster_change\("(\w+)"', source))
        facts = (ROOT / "autocad" / "Heron.AutoCAD.Bridge" / "AttributeWrites.cs").read_text(encoding="utf-8")
        assert f'UseCom = "{text_tools.USE_COM}"' in facts
