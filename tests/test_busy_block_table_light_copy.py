"""A busy AutoCAD is never a wrong answer in the block, table, light and copy tools (#189, D-100, D-128).

#189 found that the ``except`` blocks in blocks.py, tables.py, lighting.py and
between_drawings.py took AutoCAD's busy refusal (RPC_E_CALL_REJECTED) for "skip
that insert", "this cell was not set", "this AutoCAD has no EXPVALUE", "no block
called X" and "nothing with that handle". D-100 put ``raise_if_busy`` first in
each of them; tests/test_busy_sweep.py keeps new code from bringing the old way
back by reading the source. What was missing is the proof per tool, which is
this file: each tool is run with a stand-in drawing that refuses, through the
real retry loop (connection._with_retry), and must end in what a modeller can
act on - "AutoCAD stayed busy" while nothing was written, "Outcome unknown"
once a write began - never in a false failure or a quiet wrong answer.

Each class also has a control: a refusal that is NOT busy ("not there") still
gets the old, harmless fallback, so the fix did not make the tools fragile.
No AutoCAD: stand-ins only.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pythoncom
import test_block_attributes as ba
import test_drawing_copy as dc
import test_render_view as rv
import test_tables as tt

from autocad_mcp.core import connection
from autocad_mcp.tools import _shared, between_drawings, blocks, lighting, tables

REJECTED = pythoncom.com_error(-2147418111, "Call was rejected by callee.", None, None)
NOT_THERE = pythoncom.com_error(
    -2147352567, "Exception occurred.", (0, "AutoCAD", "Key not found", None, 0, -2145386476), None
)


async def _retrying_run(fn):
    """What connection.run does on the worker, without the thread: the real retry loop."""
    return connection._with_retry(fn)


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    monkeypatch.setattr(connection.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(connection, "RETRY_ATTEMPTS", 3)


def answer(coroutine) -> str:
    return asyncio.run(coroutine)


def says_busy(text: str) -> bool:
    return text.startswith("Error:") and "AutoCAD stayed busy" in text and "press Esc" in text


def says_unknown(text: str) -> bool:
    return text.startswith("Error: Outcome unknown")


# ---------------------------------------------------------------------------
# blocks.py: autocad_sync_attributes (ATTSYNC)
# ---------------------------------------------------------------------------


class BusyRef(ba.Ref):
    """An insert whose name AutoCAD will not give while it is busy."""

    def __init__(self, handle, error):
        super().__init__(handle, "VALVE TAG", "M-VALVE", [("TAG", "V-1")])
        self.error = error

    @property
    def EffectiveName(self):  # noqa: N802 - the COM name
        raise self.error

    @EffectiveName.setter
    def EffectiveName(self, value):  # noqa: N802 - Ref.__init__ sets it
        pass


@pytest.fixture
def drawing(monkeypatch):
    def make(*existing, refs=(), locked=()):
        doc = ba.Doc(*existing, refs=refs, locked=locked)

        def select(d, entity_type=None, layer=None, block_name=None, color=None, name=None):
            return ba.Selection(d.refs)

        monkeypatch.setattr(blocks, "run", _retrying_run)
        monkeypatch.setattr(blocks, "get_doc", lambda: doc)
        monkeypatch.setattr(blocks, "require_idle", lambda d: None)
        monkeypatch.setattr(blocks, "select_filtered", select)
        monkeypatch.setattr(blocks, "discard_selection_set", lambda d, n=None: None)
        monkeypatch.setattr(
            blocks, "in_plugin", lambda *a, **k: pytest.fail("a busy drawing must send the plug-in nothing")
        )
        return doc

    return make


class TestSyncAttributesBusy:
    def good(self, handle):
        return ba.Ref(handle, "VALVE TAG", "M-VALVE", [("TAG", "V-1")])

    def test_inserts_it_could_not_read_are_not_skipped_with_success(self, drawing):
        # The stand-in from #189: 4 inserts, 2 busy. It used to touch 2 and say skipped: [].
        refs = [self.good("1A"), BusyRef("1B", REJECTED), self.good("1C"), BusyRef("1D", REJECTED)]
        drawing(ba.VALVE, refs=refs)
        assert says_busy(answer(blocks.autocad_sync_attributes(block="VALVE TAG")))

    def test_an_insert_that_is_not_a_block_reference_is_still_skipped(self, drawing, monkeypatch):
        drawing(ba.VALVE, refs=[self.good("1A"), BusyRef("1B", NOT_THERE)])
        sent = []
        monkeypatch.setattr(blocks, "in_plugin", lambda op, args, what, **k: sent.append(args) or {})
        ba_result = json.loads(answer(blocks.autocad_sync_attributes(block="VALVE TAG")))
        assert [i["handle"] for i in ba_result["inserts"]] == ["1A"] and sent[0]["handles"] == ["1A"]

    def test_a_nested_insert_it_could_not_read_is_not_skipped(self, drawing):
        class BusyItem(ba.Ref):
            ObjectName = "AcDbBlockReference"

            @property
            def EffectiveName(self):  # noqa: N802
                raise REJECTED

            @EffectiveName.setter
            def EffectiveName(self, value):  # noqa: N802
                pass

        skid = ba.Block("SKID", [BusyItem("5A", "VALVE TAG", "0", [])])
        drawing(ba.VALVE, skid, refs=[self.good("1A")])
        assert says_busy(answer(blocks.autocad_sync_attributes(block="VALVE TAG", nested=True)))

    def test_a_holder_block_it_could_not_read_is_not_taken_for_a_plain_one(self, drawing):
        class BusyHolder(ba.Block):
            @property
            def IsLayout(self):  # noqa: N802
                raise REJECTED

            @IsLayout.setter
            def IsLayout(self, value):  # noqa: N802
                pass

        drawing(ba.VALVE, BusyHolder("SKID", [ba.Line()]), refs=[self.good("1A")])
        assert says_busy(answer(blocks.autocad_sync_attributes(block="VALVE TAG", nested=True)))

    def test_a_layer_it_could_not_read_is_not_taken_for_unlocked(self, drawing):
        class BusyLayers(ba.Layers):
            def Item(self, name):  # noqa: N802
                raise REJECTED

        doc = drawing(ba.VALVE, refs=[self.good("1A")])
        doc.Layers = BusyLayers()
        assert says_busy(answer(blocks.autocad_sync_attributes(block="VALVE TAG")))

    def test_a_block_it_could_not_look_up_is_not_called_missing(self, drawing):
        class BusyBlocks(ba.Blocks):
            def Item(self, key):  # noqa: N802
                raise REJECTED

        doc = drawing(ba.VALVE)
        doc.Blocks = BusyBlocks(ba.VALVE)
        text = answer(blocks.autocad_sync_attributes(block="VALVE TAG"))
        assert says_busy(text) and "no block called" not in text

    def test_a_block_that_is_really_missing_is_still_said_so(self, drawing):
        drawing()
        text = answer(blocks.autocad_sync_attributes(block="NOPE"))
        assert text.startswith("Error:") and "no block called 'NOPE'" in text and "stayed busy" not in text


# ---------------------------------------------------------------------------
# tables.py: fill_table (autocad_table_from_excel) and autocad_set_table_cells
# ---------------------------------------------------------------------------


class RefusingTable(tt.FakeTable):
    """A table that turns one kind of call away: ``busy`` names the calls, ``error`` is what it raises."""

    def __init__(self, *args, error=REJECTED, calls_refused=(), **kw):
        super().__init__(*args, **kw)
        self.error, self.calls_refused = error, set(calls_refused)

    def SetText(self, r, c, value):  # noqa: N802
        if (r, c) in self.calls_refused:
            raise self.error
        super().SetText(r, c, value)

    def SetColumnWidth(self, index, width):  # noqa: N802
        if "width" in self.calls_refused:
            raise self.error
        super().SetColumnWidth(index, width)

    def SetTextHeight(self, row_types, height):  # noqa: N802
        if "height" in self.calls_refused:
            raise self.error
        super().SetTextHeight(row_types, height)


class RefusingSpace(tt.FakeSpace):
    def __init__(self, **kw):
        super().__init__()
        self.kw = kw

    def AddTable(self, at, rows, columns, row_height, column_width):  # noqa: N802
        table = RefusingTable(rows, columns, **self.kw)
        self.added.append((rows, columns, row_height, column_width))
        self.table = table
        return table


@pytest.fixture
def table_env(monkeypatch, tmp_path):
    def make(table=None, **space_kw):
        doc = tt.FakeDoc(table=table)
        doc.ModelSpace = doc.PaperSpace = RefusingSpace(**space_kw)
        monkeypatch.setattr(tables, "run", _retrying_run)
        monkeypatch.setattr(tables, "get_doc", lambda: doc)
        monkeypatch.setattr(tables, "require_idle", lambda d: None)
        monkeypatch.setattr(tables, "apply_properties", lambda d, e, layer, aci, lt: {})
        monkeypatch.setattr(tables, "ensure_layer", lambda d, name: (None, False))
        monkeypatch.setattr(tables, "resolve_handle", lambda d, h: d.HandleToObject(h))
        return doc

    path = tmp_path / "fans.csv"
    path.write_text("TAG,FLOW\nF-01,2.5\nF-02,3\n", encoding="utf-8")
    return make, str(path)


class TestFillTableBusy:
    """Cells are written after the undo mark: a busy refusal is OUTCOME UNKNOWN, not 'not_set' and DONE."""

    def fill(self, table_env, **space_kw):
        make, path = table_env
        make(**space_kw)
        return answer(tables.autocad_table_from_excel(path=path, position=[0, 0], title="FANS", text_height=25))

    def test_a_busy_cell_is_outcome_unknown(self, table_env):
        assert says_unknown(self.fill(table_env, calls_refused={(2, 0)}))

    def test_a_busy_title_is_outcome_unknown(self, table_env):
        assert says_unknown(self.fill(table_env, calls_refused={(0, 0)}))

    def test_a_busy_column_width_is_outcome_unknown(self, table_env):
        assert says_unknown(self.fill(table_env, calls_refused={"width"}))

    def test_a_busy_text_height_is_outcome_unknown(self, table_env):
        assert says_unknown(self.fill(table_env, calls_refused={"height"}))

    def test_a_cell_autocad_really_refuses_is_still_listed_not_set(self, table_env):
        text = self.fill(table_env, error=NOT_THERE, calls_refused={(2, 0)})
        assert not text.startswith("Error") and "cell 3,1" in text and "Outcome unknown" not in text


class TestSetTableCellsBusy:
    def edit(self, table_env, **kw):
        make, _path = table_env
        table = RefusingTable(rows=4, columns=3, **kw)
        make(table=table)
        return answer(tables.autocad_set_table_cells(
            handle="2F", cells=[{"cell": "A2", "value": "x"}, {"cell": "B2", "value": "y"}],
        ))  # fmt: skip

    def test_a_busy_cell_is_outcome_unknown_not_a_refused_cell(self, table_env):
        text = self.edit(table_env, calls_refused={(1, 1)})
        assert says_unknown(text) and "refused" not in text

    def test_a_cell_autocad_really_refuses_is_still_listed(self, table_env):
        result = json.loads(self.edit(table_env, error=NOT_THERE, calls_refused={(1, 1)}))
        assert [r["cell"] for r in result["refused"]] == ["B2"] and result["changed"] == 1


# ---------------------------------------------------------------------------
# lighting.py: autocad_set_render_exposure, autocad_list_lights
# ---------------------------------------------------------------------------


class BusyVariableDoc(rv.Doc):
    """A drawing whose variable reads are turned away: all of them, or from the n-th one on."""

    def __init__(self, busy=(), after=0, error=REJECTED, **variables):
        super().__init__(**variables)
        self.busy, self.after, self.error, self.reads = set(busy), after, error, 0

    def GetVariable(self, name):  # noqa: N802
        self.reads += 1
        if name in self.busy and self.reads > self.after:
            raise self.error
        return super().GetVariable(name)


@pytest.fixture
def light_env(monkeypatch):
    def make(doc=None, **kw):
        doc = doc or BusyVariableDoc(**kw)
        fake = rv.Plugin(doc)
        monkeypatch.setattr(lighting, "run", _retrying_run)
        monkeypatch.setattr(lighting, "get_doc", lambda: doc)
        monkeypatch.setattr(lighting, "require_idle", lambda d: None)
        monkeypatch.setattr(_shared, "plugin_runner", lambda: fake)
        return doc

    return make


class TestRenderExposureBusy:
    def test_a_busy_read_is_not_this_autocad_did_not_answer(self, light_env):
        doc = light_env(busy={"EXPVALUE"})
        text = answer(lighting.autocad_set_render_exposure(exposure=7.5))
        assert says_busy(text) and "did not answer" not in text and "Nothing was changed" not in text
        assert doc.written == []

    def test_a_busy_read_back_after_the_write_is_outcome_unknown(self, light_env):
        # First read (the value before) answers; the one after the write is refused.
        doc = light_env(busy={"EXPVALUE"}, after=1)
        text = answer(lighting.autocad_set_render_exposure(exposure=7.5))
        assert says_unknown(text) and doc.written == [("EXPVALUE", 7.5)]

    def test_a_busy_write_is_outcome_unknown_not_not_set(self, light_env):
        class BusyWrite(BusyVariableDoc):
            def SetVariable(self, name, value):  # noqa: N802
                raise REJECTED

        light_env(doc=BusyWrite())
        assert says_unknown(answer(lighting.autocad_set_render_exposure(exposure=7.5)))

    def test_a_variable_this_autocad_really_lacks_is_still_said_with_the_palette(self, light_env):
        doc = light_env()
        del doc.vars["EXPVALUE"]
        text = answer(lighting.autocad_set_render_exposure(exposure=7.5))
        assert "RENDEREXPOSURE" in text and "Nothing was changed" in text


class TestListLightsBusy:
    def test_a_busy_exposure_read_is_not_a_null_exposure(self, light_env):
        light_env(busy={"EXPVALUE"})
        text = answer(lighting.autocad_list_lights())
        assert says_busy(text) and "did not answer" not in text

    def test_a_variable_this_autocad_lacks_is_still_null(self, light_env):
        doc = light_env()
        del doc.vars["EXPVALUE"]
        out = json.loads(answer(lighting.autocad_list_lights()))
        assert out["exposure"]["exposure"] is None and "RENDEREXPOSURE" in out["exposure"]["note"]


# ---------------------------------------------------------------------------
# between_drawings.py: autocad_copy_from_drawing
# ---------------------------------------------------------------------------


class BusySource(dc.Doc):
    """The drawing copied from, whose answers are turned away: a handle, an owner, a block."""

    def __init__(self, *args, busy_handles=(), busy_blocks=False, busy_owner=(), busy_copy=False, **kw):
        super().__init__(*args, **kw)
        self.busy_handles, self.busy_blocks = set(busy_handles), busy_blocks
        self.busy_owner, self.busy_copy = set(busy_owner), busy_copy

    def HandleToObject(self, handle):  # noqa: N802
        if handle in self.busy_handles:
            raise REJECTED
        return super().HandleToObject(handle)

    def CopyObjects(self, objects, owner):  # noqa: N802
        if self.busy_copy:
            raise REJECTED
        return super().CopyObjects(objects, owner)


@pytest.fixture
def copy_env(monkeypatch):
    def make(**busy):
        target, source = dc.drawings()
        source = BusySource(
            source.Name, objects=list(source.objects.values()), definitions=source.Blocks.definitions, **busy
        )
        app = dc.App(target, source)
        monkeypatch.setattr(between_drawings, "run", _retrying_run)
        monkeypatch.setattr(between_drawings, "get_app", lambda: app)
        monkeypatch.setattr(between_drawings, "get_doc", lambda: target)
        monkeypatch.setattr(between_drawings, "require_idle", lambda d: None)
        return target, source

    return make


class TestCopyFromDrawingBusy:
    def copy(self, handles=("1A", "1B")):
        return answer(between_drawings.autocad_copy_from_drawing(
            source="pump-room", handles=list(handles), base_point=[0, 0], to_point=[100, 0],
        ))  # fmt: skip

    def test_a_busy_handle_is_not_has_nothing_with_that_handle(self, copy_env):
        _target, source = copy_env(busy_handles={"1B"})
        text = self.copy()
        assert says_busy(text) and "has nothing with the handle" not in text and source.copies == []

    def test_a_handle_that_is_really_not_there_is_still_named(self, copy_env):
        copy_env()
        text = self.copy(("1A", "FFF"))
        assert text.startswith("Error:") and "has nothing with the handle(s) FFF" in text

    def test_a_busy_owner_read_is_not_a_shared_group(self, copy_env):
        class BusyOwner(dc.Entity):
            @property
            def OwnerID(self):  # noqa: N802
                raise REJECTED

            @OwnerID.setter
            def OwnerID(self, value):  # noqa: N802
                pass

        _target, source = copy_env()
        source.objects["1A"] = BusyOwner("1A")
        assert says_busy(self.copy(("1A",)))

    def test_a_busy_block_definition_is_not_a_shorter_list(self, copy_env):
        class BusyBlocks(dc.Blocks):
            def Item(self, key):  # noqa: N802
                if isinstance(key, str):
                    raise REJECTED
                return super().Item(key)

        _target, source = copy_env()
        source.Blocks = BusyBlocks(source.Blocks.definitions)
        assert says_busy(self.copy(("1B",)))

    def test_a_busy_copy_is_outcome_unknown_not_would_not_copy(self, copy_env):
        _target, source = copy_env(busy_copy=True)
        text = self.copy()
        assert says_unknown(text) and "would not copy" not in text
