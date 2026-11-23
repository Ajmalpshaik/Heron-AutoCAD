"""An extents preview frames model space as the plug-in measures it, not stale EXTMIN/EXTMAX (#269, D-151).

EXTMIN/EXTMAX shrink only on ZOOM Extents or All, so after an erase they can
still reach the erased object, and AutoCAD's own Extents plot frames that.
With the plug-in in the job, model space is measured object by object (the
entity_extents read with a DXF 410 "Model" filter). When that box lies well
inside EXTMIN/EXTMAX the preview uses it: the numbers, and the picture as a
window over it. No plug-in, an older one, or a bigger box: as before.
"""

from __future__ import annotations

import pytest
from test_preview_extents import PreviewDoc, _info

from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import _shared, document

# Model space after a line at 100000,100000 was erased: EXTMIN/EXTMAX still reach it.
STALE = ((0.0, 0.0, 0.0), (100010.0, 100000.0, 0.0))
SHEET = {"total": 40, "measured": 40, "min": [0.0, 0.0, 0.0], "max": [841.0, 594.0, 0.0]}


@pytest.fixture
def preview(monkeypatch):
    def make(measured=None, **kwargs):
        fake = PreviewDoc(**kwargs)
        asked = []

        async def run(fn):
            return fn()

        def faster_read(operation, args):
            asked.append((operation, args))
            return measured

        monkeypatch.setattr(document, "run", run)
        monkeypatch.setattr(document, "get_doc", lambda: fake)
        monkeypatch.setattr(document, "faster_read", faster_read)
        return fake, asked

    return make


async def test_stale_extents_give_way_to_the_plug_ins_model_space_box(preview):
    doc, asked = preview(measured=SHEET, extents=STALE)
    info = _info(await document.autocad_preview(detail=1))
    assert asked == [("entity_extents", {"filter": [[410, "Model"]]})]
    assert info["plotted"] == {"min": [0.0, 0.0], "max": [841.0, 594.0], "width": 841.0, "height": 594.0}
    assert "ZOOM Extents" in info["extents_note"]
    # The picture is a window over that box: AutoCAD's Extents plot would frame the stale one.
    first = doc.Plot.calls[0]["layout"]
    assert first["PlotType"] == document.AC_WINDOW
    assert first["Window"] == ([0.0, 0.0], [841.0, 594.0])


async def test_the_sheet_close_ups_split_the_fresh_box(preview):
    doc, _ = preview(measured=SHEET, extents=STALE, text_size=2.5)
    info = _info(await document.autocad_preview())
    # Measured right, it is an A1 sheet again, so it gets its close-ups (D-141).
    assert "detail_added" in info
    assert len(info["detail"]) == 4
    assert all(part["corner2"][0] < 1000.0 and part["corner2"][1] < 1000.0 for part in info["detail"])


async def test_extents_that_agree_keep_autocads_own_extents_plot(preview):
    doc, asked = preview(measured=SHEET)  # EXTMIN/EXTMAX are the A1 sheet too
    info = _info(await document.autocad_preview(detail=1))
    assert asked
    assert "extents_note" not in info
    assert doc.Plot.calls[0]["layout"]["PlotType"] == document.AC_EXTENTS
    assert doc.ActiveLayout.state["windows"] == []


async def test_a_plug_in_box_bigger_than_extmin_is_not_used(preview):
    # An object on a frozen layer: the plug-in measures it, a plot leaves it out.
    bigger = {**SHEET, "max": [5000.0, 5000.0, 0.0]}
    doc, _ = preview(measured=bigger)
    info = _info(await document.autocad_preview(detail=1))
    assert info["plotted"]["max"] == [841.0, 594.0]
    assert "extents_note" not in info
    assert doc.Plot.calls[0]["layout"]["PlotType"] == document.AC_EXTENTS


async def test_a_tiny_difference_is_not_called_stale(preview):
    near = {**SHEET, "max": [840.0, 594.0, 0.0]}  # a text's box, under 1 % in
    doc, _ = preview(measured=near)
    info = _info(await document.autocad_preview(detail=1))
    assert info["plotted"]["max"] == [841.0, 594.0]
    assert "extents_note" not in info


async def test_without_the_plug_in_it_is_extmin_extmax_as_before(preview):
    doc, asked = preview(measured=None, extents=STALE)
    info = _info(await document.autocad_preview(detail=1))
    assert asked
    assert info["plotted"]["max"] == [100010.0, 100000.0]
    assert "extents_note" not in info
    assert doc.Plot.calls[0]["layout"]["PlotType"] == document.AC_EXTENTS


async def test_nothing_measured_is_extmin_extmax_as_before(preview):
    doc, _ = preview(measured={"total": 2, "measured": 0, "min": None, "max": None}, extents=STALE)
    info = _info(await document.autocad_preview(detail=1))
    assert info["plotted"]["max"] == [100010.0, 100000.0]


async def test_a_paper_layout_is_measured_as_a_sheet_not_as_model_space(preview):
    # D-154 (#281) measures sheets too, by their own name and without their overall viewport.
    # A plug-in answer that does not say it left the viewport out is not used: PEXTMIN/PEXTMAX as before.
    doc, asked = preview(measured=SHEET, model=False)
    info = _info(await document.autocad_preview(detail=1))
    assert asked == [("entity_extents", {"filter": [[410, "Sheet-01"]], "leave_out_layout_viewports": True})]
    assert info["plotted"]["max"] == [420.0, 297.0]


async def test_an_older_plug_in_that_refuses_the_space_filter_reads_over_com(monkeypatch):
    """Plug-in 1.8.1 refuses DXF 410 as its own refusal; faster_read answers None (D-114)."""
    fake = PreviewDoc(extents=STALE)

    async def run(fn):
        return fn()

    def old_runner(operation, args):
        raise AutocadError("Heron in AutoCAD filters a read only by type, layer, block name and colour. Nothing was changed.")

    monkeypatch.setattr(document, "run", run)
    monkeypatch.setattr(document, "get_doc", lambda: fake)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: old_runner)
    monkeypatch.setattr(_shared, "plugin_version", lambda: "1.8.1")
    info = _info(await document.autocad_preview(detail=1))
    assert info["plotted"]["max"] == [100010.0, 100000.0]
    assert "extents_note" not in info
