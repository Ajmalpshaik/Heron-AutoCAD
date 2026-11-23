"""A sheet's extents preview frames what is on the sheet, not stale PEXTMIN/PEXTMAX (#281, D-154).

PEXTMIN/PEXTMAX shrink only on ZOOM Extents or All, like EXTMIN/EXTMAX (D-151).
With the plug-in in the job, the sheet is measured object by object: the
entity_extents read with a DXF 410 filter of the sheet's own name, and its
overall viewport (the paper-space view, whose box is the screen) left out. The
plug-in says it left it out; one that does not is not believed. When the box
lies well inside PEXTMIN/PEXTMAX the preview uses it, as a window plot. No
plug-in, an older one, or a bigger box: PEXTMIN/PEXTMAX as before.
"""

from __future__ import annotations

import pytest
from test_preview_extents import PreviewDoc, _info

from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import _shared, document

# An A1 sheet after a note far off the paper was erased: PEXTMIN/PEXTMAX still reach it.
STALE = {"PEXTMIN": (0.0, 0.0, 0.0), "PEXTMAX": (5000.0, 3000.0, 0.0)}
MEASURED = {"layout_viewports": "left out", "total": 12, "measured": 11,
            "min": [0.0, 0.0, 0.0], "max": [841.0, 594.0, 0.0]}


@pytest.fixture
def sheet(monkeypatch):
    def make(measured=None, name="Sheet-01", pext=None, **kwargs):
        fake = PreviewDoc(model=False, **kwargs)
        fake.ActiveLayout.state["Name"] = name
        fake.vars.update(pext or STALE)
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


async def test_stale_pextmin_gives_way_to_the_plug_ins_sheet_box(sheet):
    doc, asked = sheet(measured=MEASURED)
    info = _info(await document.autocad_preview(detail=1))
    assert asked == [("entity_extents", {"filter": [[410, "Sheet-01"]], "leave_out_layout_viewports": True})]
    assert info["plotted"] == {"min": [0.0, 0.0], "max": [841.0, 594.0], "width": 841.0, "height": 594.0}
    note = info["extents_note"]
    assert "PEXTMIN/PEXTMAX" in note and "ZOOM Extents" in note
    assert "'Sheet-01'" in note and "overall viewport left out" in note
    # A window over that box: AutoCAD's Extents plot would frame the stale one.
    first = doc.Plot.calls[0]["layout"]
    assert first["PlotType"] == document.AC_WINDOW
    assert first["Window"] == ([0.0, 0.0], [841.0, 594.0])


async def test_the_close_ups_split_the_fresh_sheet_box(sheet):
    doc, _ = sheet(measured=MEASURED, text_size=2.5)
    info = _info(await document.autocad_preview())
    assert "detail_added" in info
    assert len(info["detail"]) == 4
    assert all(part["corner2"][0] < 1000.0 and part["corner2"][1] < 1000.0 for part in info["detail"])


async def test_a_plug_in_that_does_not_say_it_left_the_viewport_out_is_not_believed(sheet):
    # Built before this change: it ignores the flag, so its box holds the screen's own viewport.
    old = {k: v for k, v in MEASURED.items() if k != "layout_viewports"}
    doc, asked = sheet(measured=old)
    info = _info(await document.autocad_preview(detail=1))
    assert asked
    assert info["plotted"]["max"] == [5000.0, 3000.0]
    assert "extents_note" not in info
    assert doc.Plot.calls[0]["layout"]["PlotType"] == document.AC_EXTENTS


async def test_without_the_plug_in_it_is_pextmin_pextmax_as_before(sheet):
    doc, _ = sheet(measured=None)
    info = _info(await document.autocad_preview(detail=1))
    assert info["plotted"]["max"] == [5000.0, 3000.0]
    assert "extents_note" not in info
    assert doc.Plot.calls[0]["layout"]["PlotType"] == document.AC_EXTENTS
    assert doc.ActiveLayout.state["windows"] == []


async def test_a_sheet_box_that_agrees_keeps_autocads_own_extents_plot(sheet):
    doc, _ = sheet(measured=MEASURED, pext={"PEXTMIN": (0.0, 0.0, 0.0), "PEXTMAX": (841.0, 594.0, 0.0)})
    info = _info(await document.autocad_preview(detail=1))
    assert "extents_note" not in info
    assert doc.Plot.calls[0]["layout"]["PlotType"] == document.AC_EXTENTS


async def test_a_bigger_sheet_box_is_not_used(sheet):
    # A viewport frame on a frozen layer: the plug-in measures it, a plot leaves it out.
    bigger = {**MEASURED, "max": [6000.0, 3000.0, 0.0]}
    doc, _ = sheet(measured=bigger)
    info = _info(await document.autocad_preview(detail=1))
    assert info["plotted"]["max"] == [5000.0, 3000.0]
    assert "extents_note" not in info


async def test_nothing_measured_on_the_sheet_is_pextmin_as_before(sheet):
    doc, _ = sheet(measured={"layout_viewports": "left out", "total": 1, "measured": 0, "min": None, "max": None})
    info = _info(await document.autocad_preview(detail=1))
    assert info["plotted"]["max"] == [5000.0, 3000.0]


async def test_a_sheet_name_with_wildcard_characters_matches_only_itself(sheet):
    _, asked = sheet(measured=MEASURED, name="M-101, rev.A #2")
    await document.autocad_preview(detail=1)
    assert asked[0][1]["filter"] == [[410, "M-101`, rev`.A `#2"]]


@pytest.mark.parametrize(
    ("name", "plain"),
    [("Model", "Model"), ("A1-01", "A1-01"), ("*", "`*"), ("[A]?~@`", "`[A`]`?`~`@``")],
)
def test_plain_name_escapes_each_wildcard(name, plain):
    assert document._plain_name(name) == plain


async def test_an_older_plug_in_that_refuses_the_space_filter_previews_as_before(monkeypatch):
    """Plug-in 1.8.1 refuses DXF 410 as its own refusal; faster_read answers None (D-114)."""
    fake = PreviewDoc(model=False)
    fake.vars.update(STALE)

    async def run(fn):
        return fn()

    def old_runner(operation, args):
        raise AutocadError("Heron in AutoCAD filters a read only by type, layer, block name and colour. Nothing was changed.")

    monkeypatch.setattr(document, "run", run)
    monkeypatch.setattr(document, "get_doc", lambda: fake)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: old_runner)
    monkeypatch.setattr(_shared, "plugin_version", lambda: "1.8.1")
    info = _info(await document.autocad_preview(detail=1))
    assert info["plotted"]["max"] == [5000.0, 3000.0]
    assert "extents_note" not in info
