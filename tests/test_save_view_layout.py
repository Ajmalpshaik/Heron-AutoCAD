"""autocad_save_view(replace=true) never deletes a layout's view (#190, D-128).

The docstring said a sheet's view of that name is refused even with
replace=true, but the code deleted any view of that name. A sheet's saved view
("DETAIL-A") was then replaced by a model view. A view is the Model tab's only
when its LayoutId is the Model layout's own ObjectID; anything else is refused
in plain words before the undo mark, so nothing is deleted. No AutoCAD:
stand-ins only.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pythoncom
import test_render_setup as rs

from autocad_mcp.core import connection
from autocad_mcp.tools import views

MODEL_ID = 0x2B
SHEET_ID = 0x7C
REJECTED = pythoncom.com_error(-2147418111, "Call was rejected by callee.", None, None)


class SavedView(rs.View):
    def __init__(self, name, layout_id=MODEL_ID):
        super().__init__(name)
        if layout_id is None:
            del self.LayoutId  # a view AutoCAD does not say the layout of
        else:
            self.LayoutId = layout_id

    def __setattr__(self, name, value):
        # COM hands back plain numbers for a point written as a VARIANT.
        super().__setattr__(name, tuple(value.value) if hasattr(value, "value") else value)


class Layout:
    ObjectID = MODEL_ID
    ObjectID32 = MODEL_ID


class Layouts:
    def Item(self, name):  # noqa: N802 - the COM name
        assert name == "Model"
        return Layout()


class ViewList(rs.Views):
    def __init__(self, *saved):
        self.items = list(saved)
        self.added = []

    def Add(self, name):  # noqa: N802
        view = SavedView(name)
        self.items.append(view)
        self.added.append(name)
        return view


class SheetDoc(rs.ViewDoc):
    def __init__(self, *saved):
        super().__init__()
        self.Views = ViewList(*saved)
        self.Layouts = Layouts()
        self.Application = type("App", (), {"ZoomWindow": lambda self, a, b: None})()


WINDOW = {"corner1": [0, 0], "corner2": [100, 50]}


@pytest.fixture
def drawing(monkeypatch):
    def make(*saved, run=rs._now):
        doc = SheetDoc(*saved)
        monkeypatch.setattr(views, "run", run)
        monkeypatch.setattr(views, "get_doc", lambda: doc)
        monkeypatch.setattr(views, "require_idle", lambda d: None)
        monkeypatch.setattr(views, "VIEW_COMMAND_WAIT_S", 0.05)
        return doc

    return make


def refused(text: str) -> bool:
    return text.startswith("Error:") and "view of a layout (a sheet)" in text and "another name" in text


class TestAWindowView:
    def test_a_layouts_view_is_refused_with_replace_and_not_deleted(self, drawing):
        sheet = SavedView("DETAIL-A", SHEET_ID)
        doc = drawing(sheet)
        text = asyncio.run(views.autocad_save_view(name="DETAIL-A", replace=True, **WINDOW))
        assert refused(text) and "nothing was changed" in text
        assert not sheet.deleted and doc.Views.added == []

    def test_the_name_is_matched_whatever_the_case(self, drawing):
        sheet = SavedView("DETAIL-A", SHEET_ID)
        drawing(sheet)
        assert refused(asyncio.run(views.autocad_save_view(name="detail-a", replace=True, **WINDOW)))
        assert not sheet.deleted

    def test_a_model_view_is_still_replaced(self, drawing):
        old = SavedView("PUMP-AREA", MODEL_ID)
        doc = drawing(old)
        out = json.loads(asyncio.run(views.autocad_save_view(name="PUMP-AREA", replace=True, **WINDOW)))
        assert out["replaced"] is True and old.deleted and doc.Views.added == ["PUMP-AREA"]

    def test_without_replace_it_still_says_the_name_is_taken(self, drawing):
        drawing(SavedView("DETAIL-A", SHEET_ID))
        text = asyncio.run(views.autocad_save_view(name="DETAIL-A", **WINDOW))
        assert text.startswith("Error:") and "already has a view called 'DETAIL-A'" in text

    def test_a_view_whose_layout_is_not_said_is_not_deleted(self, drawing):
        unknown = SavedView("DETAIL-A", layout_id=None)
        doc = drawing(unknown)
        text = asyncio.run(views.autocad_save_view(name="DETAIL-A", replace=True, **WINDOW))
        assert text.startswith("Error:") and "did not say which tab" in text and "another name" in text
        assert not unknown.deleted and doc.Views.added == []

    def test_a_view_with_layout_id_zero_is_not_deleted(self, drawing):
        # What a model view might report if AutoCAD keeps no layout for it: never deleted on a guess.
        zero = SavedView("PUMP-AREA", layout_id=0)
        doc = drawing(zero)
        text = asyncio.run(views.autocad_save_view(name="PUMP-AREA", replace=True, **WINDOW))
        assert text.startswith("Error:") and "did not say which tab" in text
        assert not zero.deleted and doc.Views.added == []

    def test_a_busy_read_of_the_layout_goes_up_and_nothing_is_deleted(self, drawing, monkeypatch):
        monkeypatch.setattr(connection.time, "sleep", lambda seconds: None)
        monkeypatch.setattr(connection, "RETRY_ATTEMPTS", 3)

        class BusyView(SavedView):
            @property
            def LayoutId(self):  # noqa: N802
                raise REJECTED

            @LayoutId.setter
            def LayoutId(self, value):  # noqa: N802
                pass

        async def retrying(fn):
            return connection._with_retry(fn)

        busy = BusyView("DETAIL-A")
        doc = drawing(busy, run=retrying)
        text = asyncio.run(views.autocad_save_view(name="DETAIL-A", replace=True, **WINDOW))
        assert text.startswith("Error:") and "AutoCAD stayed busy" in text and "view of a layout" not in text
        assert not busy.deleted and doc.Views.added == []


class TestTheScreenView:
    def test_a_layouts_view_is_refused_with_replace_and_not_deleted(self, drawing):
        sheet = SavedView("DETAIL-A", SHEET_ID)
        doc = drawing(sheet)
        text = asyncio.run(views.autocad_save_view(name="DETAIL-A", from_screen=True, replace=True))
        assert refused(text)
        assert not sheet.deleted and doc.sent == []

    def test_a_model_view_is_still_replaced(self, drawing):
        old = SavedView("LIVING-3D", MODEL_ID)
        doc = drawing(old)
        out = json.loads(asyncio.run(views.autocad_save_view(name="LIVING-3D", from_screen=True, replace=True)))
        assert out["replaced"] is True and old.deleted and doc.sent == ["_.-VIEW _Save LIVING-3D\n"]
