"""Copying objects between open drawings (D-83, issue #106), without AutoCAD.

What is checked: which open drawing is meant, what a copy brings along (the
layers, styles and blocks the target lacks, blocks inside blocks) and what is
the target's own, how far the copies move, and what the tool sends to AutoCAD.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.acad.drawing_copy import (
    blocks_needed,
    find_open,
    offset,
    what_comes_along,
)
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import between_drawings

OPEN = [("plan.dwg", r"D:\jobs\plan.dwg"), ("pump-room.dwg", r"D:\jobs\pump-room.dwg"), ("Drawing1.dwg", "Drawing1.dwg")]


class TestFindOpen:
    @pytest.mark.parametrize("wanted", ["pump-room.dwg", "PUMP-ROOM", r"D:\jobs\pump-room.dwg", "d:/jobs/PUMP-ROOM.dwg"])
    def test_by_name_or_path_any_case_either_slash(self, wanted):
        assert find_open(OPEN, wanted) == 1

    def test_by_name(self):
        assert find_open(OPEN, "pump-room") == 1

    def test_only_a_drawing_extension_is_left_off(self):
        """Review 2026-11-21: 'Level.01' found Level.dwg, because '.01' was taken for an extension."""
        drawings = [("Level.dwg", r"D:\a\Level.dwg"), ("Level.01.dwg", r"D:\a\Level.01.dwg")]
        assert find_open(drawings, "Level.01") == 1
        assert find_open(drawings, "Level.01.DWG") == 1
        assert find_open(drawings, "level") == 0

    def test_not_open_lists_what_is(self):
        with pytest.raises(ValueError, match="plan.dwg, pump-room.dwg, Drawing1.dwg"):
            find_open(OPEN, "site.dwg")

    def test_two_with_one_name_asks_for_the_path(self):
        with pytest.raises(ValueError, match="full path"):
            find_open([("plan.dwg", r"D:\a\plan.dwg"), ("plan.dwg", r"D:\b\plan.dwg")], "plan")


class TestWhatComesAlong:
    INSIDE = {
        "SKID": {"layers": ["M-EQPT", "0"], "blocks": ["PUMP", "VALVE"], "text_styles": ["ROMANS"]},
        "PUMP": {"layers": ["M-EQPT"], "blocks": ["MOTOR"]},
        "MOTOR": {"layers": ["E-MOTOR"], "linetypes": ["HIDDEN"]},
        "VALVE": {"layers": ["M-VALVE"]},
    }

    def test_blocks_inside_blocks_are_followed(self):
        assert blocks_needed(["SKID"], self.INSIDE) == ["MOTOR", "PUMP", "SKID", "VALVE"]

    def test_a_block_that_inserts_itself_is_followed_once(self):
        assert blocks_needed(["A"], {"A": {"blocks": ["B"]}, "B": {"blocks": ["A"]}}) == ["A", "B"]

    def test_what_the_target_lacks_comes_and_what_it_has_is_its_own(self):
        uses = {"layers": ["M-PIPE", "0"], "blocks": ["SKID"], "linetypes": ["ByLayer"], "dim_styles": ["ISO-25"]}
        target = {"layers": ["0", "m-eqpt"], "blocks": ["VALVE"], "text_styles": ["Standard"], "dim_styles": ["ISO-25"]}
        along = what_comes_along(uses, self.INSIDE, target)
        assert along["brought_in"] == {
            "layers": ["E-MOTOR", "M-PIPE", "M-VALVE"],
            "linetypes": ["HIDDEN"],
            "text_styles": ["ROMANS"],
            "blocks": ["MOTOR", "PUMP", "SKID"],
        }
        assert along["already_here"] == {"layers": ["M-EQPT"], "dim_styles": ["ISO-25"], "blocks": ["VALVE"]}

    def test_names_every_drawing_has_and_unnamed_blocks_are_not_listed(self):
        uses = {"layers": ["0"], "linetypes": ["Continuous", "ByBlock"], "text_styles": ["Standard"], "blocks": ["*U12", "*D3"]}
        assert what_comes_along(uses, {}, {}) == {"brought_in": {}, "already_here": {}}


class TestOffset:
    def test_from_the_base_point_to_the_point_in_the_target(self):
        assert offset([100, 200], [5100, 2200]) == [5000.0, 2000.0, 0.0]

    def test_no_point_keeps_the_coordinates(self):
        assert offset([100, 200], None) == [0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# The tool against fake drawings
# ---------------------------------------------------------------------------


class Named:
    def __init__(self, name):
        self.Name = name


class Collection:
    def __init__(self, *names):
        self.items = [Named(n) for n in names]

    @property
    def Count(self):
        return len(self.items)

    def Item(self, i):
        return self.items[i]


class Entity:
    def __init__(self, handle, kind="AcDbLine", layer="M-PIPE", owner=1, **extra):
        self.Handle, self.ObjectName, self.Layer, self.Linetype, self.OwnerID = handle, kind, layer, "ByLayer", owner
        self.moved = None
        for key, value in extra.items():
            setattr(self, key, value)

    def Move(self, start, end):
        self.moved = (tuple(getattr(start, "value", start)), tuple(getattr(end, "value", end)))


class BlockDef:
    def __init__(self, *items):
        self.items = list(items)

    @property
    def Count(self):
        return len(self.items)

    def Item(self, i):
        return self.items[i]


class Blocks(Collection):
    def __init__(self, definitions, *names):
        super().__init__(*names)
        self.definitions = definitions

    def Item(self, key):
        if isinstance(key, int):
            return self.items[key]
        return self.definitions[key]


class Doc:
    def __init__(self, name, objects=(), definitions=None, layers=("0",), blocks=()):
        self.Name, self.FullName = name, "D:\\jobs\\" + name
        self.objects = {o.Handle: o for o in objects}
        self.Layers, self.Linetypes = Collection(*layers), Collection("ByLayer", "Continuous")
        self.TextStyles, self.DimStyles = Collection("Standard"), Collection("ISO-25")
        self.Blocks = Blocks(definitions or {}, *blocks)
        self.ModelSpace, self.PaperSpace = Named("*Model_Space"), Named("*Paper_Space")
        self.copies = []
        self.undo = []

    def HandleToObject(self, handle):
        return self.objects[handle]

    def CopyObjects(self, objects, owner):
        items = list(getattr(objects, "value", objects))
        made = tuple(Entity(f"N{len(self.copies)}{i}") for i, _ in enumerate(items))
        self.copies.append(([o.Handle for o in items], owner.Name, made))
        return made

    def StartUndoMark(self):
        self.undo.append("start")

    def EndUndoMark(self):
        self.undo.append("end")


class App:
    def __init__(self, *docs):
        self.Documents = type("Docs", (), {"Count": len(docs), "Item": lambda self, i: docs[i]})()


@pytest.fixture
def env(monkeypatch):
    def make(target, *others):
        app = App(target, *others)

        async def run(fn):
            return fn()

        monkeypatch.setattr(between_drawings, "run", run)
        monkeypatch.setattr(between_drawings, "get_app", lambda: app)
        monkeypatch.setattr(between_drawings, "get_doc", lambda: target)
        monkeypatch.setattr(between_drawings, "require_idle", lambda d: None)
        return app

    return make


def answer(coroutine) -> dict:
    text = asyncio.run(coroutine)
    assert not text.startswith("Error:"), text
    return json.loads(text)


def drawings():
    skid = BlockDef(Entity("B1", layer="M-EQPT"), Entity("B2", kind="AcDbBlockReference", layer="M-EQPT", Name="MOTOR", EffectiveName="MOTOR"))
    motor = BlockDef(Entity("B3", layer="E-MOTOR"))
    source = Doc(
        "pump-room.dwg",
        objects=[
            Entity("1A"),
            Entity("1B", kind="AcDbBlockReference", layer="M-EQPT", Name="SKID", EffectiveName="SKID"),
            Entity("1C", kind="AcDbMText", layer="M-ANNO", StyleName="ROMANS"),
            Entity("1D", owner=2),
        ],
        definitions={"SKID": skid, "MOTOR": motor},
    )
    target = Doc("plan.dwg", layers=("0", "M-EQPT"), blocks=("MOTOR",))
    return target, source


class TestCopyTool:
    def test_a_dry_run_lists_what_comes_along_and_copies_nothing(self, env):
        target, source = drawings()
        env(target, source)
        result = answer(between_drawings.autocad_copy_from_drawing(
            source="pump-room", handles=["1a", "1B", "1C"], base_point=[0, 0], to_point=[5000, 2000], dry_run=True,
        ))  # fmt: skip
        assert result["dry_run"] is True and result["would_copy"] == 3 and source.copies == []
        assert result["brought_in"]["layers"] == ["E-MOTOR", "M-ANNO", "M-PIPE"]
        assert result["brought_in"]["blocks"] == ["SKID"] and result["brought_in"]["text_styles"] == ["ROMANS"]
        assert result["already_here"] == {"layers": ["M-EQPT"], "blocks": ["MOTOR"]}
        assert "this drawing's own" in result["already_here_note"]

    def test_the_copy_goes_into_this_drawing_one_call_per_owner_then_moves(self, env):
        target, source = drawings()
        env(target, source)
        result = answer(between_drawings.autocad_copy_from_drawing(
            source="pump-room.dwg", handles=["1A", "1B", "1D"], base_point=[100, 100], to_point=[5100, 2100],
        ))  # fmt: skip
        assert [(handles, owner) for handles, owner, _ in source.copies] == [(["1A", "1B"], "*Model_Space"), (["1D"], "*Model_Space")]
        assert result["copied"] == 3 and len(result["handles"]) == 3
        made = [obj for _, _, objs in source.copies for obj in objs]
        assert all(obj.moved == ((100.0, 100.0, 0.0), (5100.0, 2100.0, 0.0)) for obj in made)
        assert target.undo == ["start", "end"] and source.undo == []

    def test_no_to_point_keeps_the_coordinates(self, env):
        target, source = drawings()
        env(target, source)
        answer(between_drawings.autocad_copy_from_drawing(source="pump-room", handles=["1A"], base_point=[0, 0]))
        assert source.copies[0][2][0].moved is None

    def test_paper_space_is_this_drawings_sheet(self, env):
        target, source = drawings()
        env(target, source)
        answer(between_drawings.autocad_copy_from_drawing(source="pump-room", handles=["1A"], base_point=[0, 0], space="paper"))
        assert source.copies[0][1] == "*Paper_Space"

    def test_a_handle_that_is_not_in_the_source_stops_it_all(self, env):
        target, source = drawings()
        env(target, source)
        text = asyncio.run(between_drawings.autocad_copy_from_drawing(source="pump-room", handles=["1A", "FFF"], base_point=[0, 0]))
        assert text.startswith("Error:") and "FFF" in text and "Nothing was copied" in text and source.copies == []

    def test_each_source_object_is_named_so_a_wrong_handle_shows(self, env):
        # #218 item 7: a handle read in plan.dwg names some other object in pump-room.dwg.
        target, source = drawings()
        env(target, source)
        for dry_run in (True, False):
            result = answer(between_drawings.autocad_copy_from_drawing(
                source="pump-room", handles=["1A", "1C"], base_point=[0, 0], dry_run=dry_run,
            ))  # fmt: skip
            assert result["source_objects"] == [
                {"handle": "1A", "type": "AcDbLine", "layer": "M-PIPE"},
                {"handle": "1C", "type": "AcDbMText", "layer": "M-ANNO"},
            ]
            assert "source_objects_left_out" not in result

    def test_a_long_list_of_source_objects_is_cut_and_counted(self, env):
        target, source = drawings()
        source.objects.update({f"2{i:03X}": Entity(f"2{i:03X}") for i in range(60)})
        env(target, source)
        result = answer(between_drawings.autocad_copy_from_drawing(
            source="pump-room", handles=[f"2{i:03X}" for i in range(60)], base_point=[0, 0], dry_run=True,
        ))  # fmt: skip
        assert len(result["source_objects"]) == between_drawings.MOST_LISTED
        assert result["source_objects_left_out"] == 60 - between_drawings.MOST_LISTED

    def test_a_handle_that_names_no_drawn_object_there_stops_it_all(self, env):
        # A layer (no Layer of its own) under that handle in the source: never copied.
        target, source = drawings()
        layer = Named("M-PIPE")
        layer.Handle, layer.ObjectName = "10", "AcDbLayerTableRecord"
        source.objects["10"] = layer
        env(target, source)
        text = asyncio.run(between_drawings.autocad_copy_from_drawing(source="pump-room", handles=["1A", "10"], base_point=[0, 0]))
        assert text.startswith("Error:") and "10 (AcDbLayerTableRecord)" in text and "not a drawn object" in text
        assert "Nothing was copied" in text and source.copies == []

    def test_the_active_drawing_as_source_points_at_copy_entities(self, env):
        target, source = drawings()
        env(target, source)
        text = asyncio.run(between_drawings.autocad_copy_from_drawing(source="plan", handles=["1A"], base_point=[0, 0]))
        assert text.startswith("Error:") and "autocad_copy_entities" in text

    def test_a_drawing_that_is_not_open_is_named(self, env):
        target, source = drawings()
        env(target, source)
        text = asyncio.run(between_drawings.autocad_copy_from_drawing(source="site", handles=["1A"], base_point=[0, 0]))
        assert text.startswith("Error:") and "plan.dwg, pump-room.dwg" in text


class TestCopiedResult:
    def test_with_or_without_the_id_pairs(self):
        a, b = object(), object()
        assert between_drawings._copied((a, b)) == [a, b]
        assert between_drawings._copied(((a, b), ((1, 2),))) == [a, b]
        assert between_drawings._copied(None) == []


def test_level():
    assert risk_of("autocad_copy_from_drawing") is Risk.CHANGE
