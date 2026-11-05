"""autocad_make_block: turn drawn objects into a named block and put the block in their place.

Ajmal, 2026-10-26: elbows, fittings and parts must be blocks, "otherwise the
manual drawing person cannot do anything".
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.tools import blocks


class Obj:
    def __init__(self, handle):
        self.Handle, self.deleted = handle, False

    def Delete(self):
        self.deleted = True


class Insert:
    def __init__(self, name, at):
        self.Name, self.at, self.Handle, self.Layer = name, at, "9F", "0"
        self.ObjectName, self.Document = "AcDbBlockReference", None


class Block:
    def __init__(self, name):
        self.Name = name


class Blocks:
    def __init__(self, existing=()):
        self.items = {n: Block(n) for n in existing}

    def Item(self, name):
        return self.items[name]

    def Add(self, base, name):
        self.items[name] = Block(name)
        self.items[name].base = base
        return self.items[name]


class Space:
    def __init__(self):
        self.inserts = []

    def InsertBlock(self, at, name, sx, sy, sz, rot):
        ref = Insert(name, at)
        self.inserts.append(ref)
        return ref


class Doc:
    def __init__(self, existing=()):
        self.objs = {h: Obj(h) for h in ("1A", "1B", "1C")}
        self.Blocks = Blocks(existing)
        self.ModelSpace = Space()
        self.copied = None

    def HandleToObject(self, h):
        return self.objs[h]

    def CopyObjects(self, objects, owner):
        self.copied = ([o.Handle for o in getattr(objects, "value", objects)], owner.Name)

    def GetVariable(self, name):
        return 0

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


@pytest.fixture
def setup(monkeypatch):
    def make(existing=()):
        doc = Doc(existing)

        async def run(fn):
            return fn()

        monkeypatch.setattr(blocks, "run", run)
        monkeypatch.setattr(blocks, "get_doc", lambda: doc)
        monkeypatch.setattr(blocks, "require_idle", lambda d: None)
        monkeypatch.setattr(blocks, "get_space", lambda d, s: d.ModelSpace)
        monkeypatch.setattr(blocks, "apply_properties", lambda d, e, layer, aci, lt: {})
        monkeypatch.setattr(blocks, "resolve_handles", lambda d, hs: [d.HandleToObject(h) for h in hs])
        return doc

    return make


def call(**kw) -> dict:
    return json.loads(asyncio.run(blocks.autocad_make_block(**kw)))


def test_objects_become_one_block_in_the_same_place(setup):
    doc = setup()
    result = call(name="SHS 100x100x5 POST", handles=["1A", "1B"], base_point=[0, 352])
    assert doc.copied == (["1A", "1B"], "SHS 100x100x5 POST")
    assert doc.objs["1A"].deleted and doc.objs["1B"].deleted and not doc.objs["1C"].deleted
    (ref,) = doc.ModelSpace.inserts
    assert ref.Name == "SHS 100x100x5 POST"
    assert result["created"] is True and result["handle"] == "9F" and result["block"] == "SHS 100x100x5 POST"


def test_keep_originals_leaves_the_geometry_and_inserts_nothing(setup):
    doc = setup()
    result = call(name="M12 ANCHOR", handles=["1A"], base_point=[0, 0], keep_originals=True)
    assert not doc.objs["1A"].deleted
    assert doc.ModelSpace.inserts == []
    assert result["handle"] is None


def test_an_existing_block_name_is_refused_before_anything_changes(setup):
    doc = setup(existing=("M12 ANCHOR",))
    result = asyncio.run(blocks.autocad_make_block(name="M12 ANCHOR", handles=["1A"], base_point=[0, 0]))
    assert result.startswith("Error:") and "already" in result
    assert doc.copied is None and not doc.objs["1A"].deleted


def test_make_block_is_a_change_level_tool():
    from autocad_mcp.core.risk import Risk, risk_of

    assert risk_of("autocad_make_block") is Risk.CHANGE


def test_a_light_goes_into_the_block_with_its_fitting(setup):
    """A downlight's can and its light become one block (D-42).

    make_block copies whatever it is handed with CopyObjects, which deep-clones
    any object, a light (AcDbLight) included; nothing filters by type.
    """
    doc = setup()
    doc.objs["1B"].ObjectName = "AcDbLight"
    call(name="DL-01 DOWNLIGHT", handles=["1A", "1B"], base_point=[0, 0, 2950])
    assert doc.copied == (["1A", "1B"], "DL-01 DOWNLIGHT")
    assert doc.objs["1B"].deleted
