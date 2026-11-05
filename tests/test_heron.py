"""Heron AI for AutoCAD: risk levels and server start-up options."""

from __future__ import annotations

import asyncio

from autocad_mcp.core.registry import mcp
from autocad_mcp.core.risk import RISK, Risk, risk_of
from autocad_mcp.tools import register_all

register_all()


def _registered() -> set[str]:
    return {tool.name for tool in asyncio.run(mcp.list_tools())}


def test_every_registered_tool_has_a_level():
    # A tool with no level would slip past the padlocks, so this fails first.
    assert _registered() == set(RISK)


def test_levels_match_spec():
    assert risk_of("autocad_status") is Risk.READ
    assert risk_of("autocad_zoom") is Risk.VIEW
    assert risk_of("autocad_open_drawing") is Risk.VIEW
    assert risk_of("autocad_draw_line") is Risk.CHANGE
    assert risk_of("autocad_delete_entities") is Risk.CHANGE
    assert risk_of("autocad_create_layer") is Risk.CHANGE
    assert risk_of("autocad_save_drawing") is Risk.PUBLISH
    assert risk_of("autocad_export") is Risk.PUBLISH
    assert risk_of("autocad_run_lisp") is Risk.ADMIN
    assert risk_of("autocad_send_command") is Risk.ADMIN
    assert risk_of("autocad_set_variable") is Risk.ADMIN
    if "autocad_preview" in RISK:
        assert risk_of("autocad_preview") is Risk.READ


def test_the_a30_reads_are_read_level():
    # The plug-in turns undo recording off only for Read jobs (UndoPause), so
    # these must stay Read: moved to View, each would cost a Ctrl+Z again.
    for tool in ("autocad_list_entities", "autocad_get_variable", "autocad_preview"):
        assert risk_of(tool) is Risk.READ, tool


def test_read_only_annotation_means_read_or_view():
    # A tool that tells the client it changes nothing must not be graded
    # Change: the plug-in would record its undo steps.
    for tool in asyncio.run(mcp.list_tools()):
        if tool.annotations is not None and tool.annotations.read_only_hint:
            assert risk_of(tool.name) in (Risk.READ, Risk.VIEW), tool.name


def test_unknown_tool_has_no_level():
    try:
        risk_of("autocad_not_a_tool")
    except KeyError:
        return
    raise AssertionError("an unknown tool must not get a default level")


class FakeServer:
    def __init__(self, names):
        self.names = list(names)

    async def list_tools(self):
        class T:
            def __init__(self, name):
                self.name = name

        return [T(n) for n in self.names]

    def remove_tool(self, name):
        self.names.remove(name)


def test_read_only_keeps_only_read_and_view():
    from autocad_mcp.server import apply_read_only

    server = FakeServer(["autocad_status", "autocad_zoom", "autocad_draw_line", "autocad_export", "autocad_run_lisp"])
    removed = apply_read_only(server)
    assert server.names == ["autocad_status", "autocad_zoom"]
    assert sorted(removed) == ["autocad_draw_line", "autocad_export", "autocad_run_lisp"]


import pytest  # noqa: E402
from mcp.server.mcpserver import Image  # noqa: E402
from test_export import FakeDoc  # noqa: E402

from autocad_mcp.tools import document  # noqa: E402


@pytest.fixture
def preview_doc(monkeypatch):
    fake = FakeDoc()

    async def run(fn):
        return fn()

    monkeypatch.setattr(document, "run", run)
    monkeypatch.setattr(document, "get_doc", lambda: fake)
    return fake


async def test_preview_returns_image(preview_doc):
    result = await document.autocad_preview()
    assert isinstance(result, list)
    assert isinstance(result[0], Image)
    assert '"area": "extents"' in result[1]


async def test_preview_plots_to_png_and_restores_page_setup(preview_doc):
    before = dict(preview_doc.ActiveLayout.state)
    await document.autocad_preview()
    plotted = preview_doc.Plot.calls[0]["layout"]
    assert plotted["ConfigName"] == "PublishToWeb PNG.pc3"
    assert preview_doc.ActiveLayout.state == before


async def test_preview_plots_upright_and_puts_the_rotation_back(preview_doc):
    # A layout turned 90 degrees gave a preview on its side (2026-11-05).
    await document.autocad_preview()
    assert preview_doc.Plot.calls[0]["layout"]["PlotRotation"] == 0
    assert preview_doc.ActiveLayout.state["PlotRotation"] == 1


async def test_preview_rejects_window_without_corners(preview_doc):
    result = await document.autocad_preview(area="window")
    assert isinstance(result, str) and result.startswith("Error:")


async def test_preview_image_survives_the_mcp_layer(preview_doc):
    result = await mcp.call_tool("autocad_preview", {})
    blocks = result.content
    assert [type(b).__name__ for b in blocks] == ["ImageContent", "TextContent"]
    assert blocks[0].mime_type == "image/png"


class PointVariableDoc:
    def __init__(self):
        self.variables = {"LIMMAX": (420.0, 297.0), "UCSORG": (0.0, 0.0, 0.0)}
        self.sent = {}

    def GetVariable(self, name):
        return self.variables[name]

    def SetVariable(self, name, value):
        self.sent[name] = value
        self.variables[name] = tuple(value.value)


@pytest.fixture
def point_doc(monkeypatch):
    fake = PointVariableDoc()

    async def run(fn):
        return fn()

    monkeypatch.setattr(document, "run", run)
    monkeypatch.setattr(document, "get_doc", lambda: fake)
    return fake


async def test_set_variable_takes_a_point_as_x_comma_y(point_doc):
    """A point variable was sent the typed text itself, which AutoCAD cannot take."""
    import json

    import pythoncom

    result = json.loads(await document.autocad_set_variable(name="LIMMAX", value="42000,29700"))
    sent = point_doc.sent["LIMMAX"]
    assert sent.varianttype == pythoncom.VT_ARRAY | pythoncom.VT_R8
    assert tuple(sent.value) == (42000.0, 29700.0)
    assert result["value"] == [42000.0, 29700.0]


async def test_set_variable_refuses_a_point_with_the_wrong_number_of_values(point_doc):
    answer = await document.autocad_set_variable(name="UCSORG", value="10,20")
    assert answer.startswith("Error") and "3 numbers" in answer
    assert point_doc.sent == {}


# The -PURGE prompt's words, capitals as AutoCAD shows them. An answer is taken
# when it is the capitals, or the start of the whole word that holds them.
PURGE_PROMPT = {
    "blocks": "Blocks", "layers": "LAyers", "linetypes": "LTypes",
    "text_styles": "textSTyles", "dim_styles": "Dimstyles", "all": "All",
}


@pytest.mark.parametrize("target", sorted(PURGE_PROMPT))
def test_every_purge_answer_is_one_the_prompt_takes(target):
    """'_STyles' is neither the capitals of 'textSTyles' nor the start of the word."""
    from autocad_mcp.tools.advanced import PURGE_OPTIONS

    word = PURGE_PROMPT[target]
    typed = PURGE_OPTIONS[target].removeprefix("_")
    capitals = "".join(c for c in word if c.isupper())
    assert typed.upper() == capitals or (
        word.upper().startswith(typed.upper()) and len(typed) >= len(capitals)
    ), f"{typed!r} is not an answer the prompt word {word!r} takes"
