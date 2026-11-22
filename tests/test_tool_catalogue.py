"""docs/TOOL-CATALOGUE.md covers every tool and is not stale (tools/make_tool_catalogue.py). No AutoCAD."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from autocad_mcp.core.registry import mcp
from autocad_mcp.tools import register_all

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "docs" / "TOOL-CATALOGUE.md"


def _load():
    spec = importlib.util.spec_from_file_location("make_tool_catalogue", ROOT / "tools" / "make_tool_catalogue.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_tool_catalogue"] = module
    spec.loader.exec_module(module)
    return module


maker = _load()


@pytest.fixture(scope="module")
def names():
    register_all()
    return sorted(t.name for t in asyncio.run(mcp.list_tools()))


@pytest.fixture(scope="module")
def generated():
    return maker.generate()


def test_every_tool_is_in_a_group(names):
    assert set(names) == set(maker.GROUP_OF)


def test_catalogue_names_every_tool(names):
    text = CATALOGUE.read_text(encoding="utf-8")
    assert maker.missing_from(text, names) == [], "run python tools/make_tool_catalogue.py"
    assert f"**{len(names)}** tools" in text


def test_missing_tool_is_caught(names):
    text = CATALOGUE.read_text(encoding="utf-8").replace("### `autocad_loft`", "### `autocad_lost`")
    assert maker.missing_from(text, names) == ["autocad_loft"]


def test_catalogue_is_not_stale(generated):
    on_disk = CATALOGUE.read_text(encoding="utf-8")
    assert on_disk == generated, "docs/TOOL-CATALOGUE.md is stale: run python tools/make_tool_catalogue.py"


def test_every_section_has_every_part(generated):
    parts = ("**What it does.**", "**The problem it solves.**", "**Where to find it.**", "**How to use it.**",
             "**What it needs from you.**", "**The result to expect.**", "**Limits and versions.**", "**Live proof.**")
    sections = generated.split("\n### `")[1:]
    assert sections
    for section in sections:
        for part in parts:
            assert part in section, section.splitlines()[0]


def test_proof_lines_come_from_the_register(generated):
    # Every section ends in a proof line, and a tool that no register row names says so.
    assert generated.count("**Live proof.**") == len(maker.GROUP_OF)
    assert "**NO ROW**" in generated or "**NOT RUN**" in generated
