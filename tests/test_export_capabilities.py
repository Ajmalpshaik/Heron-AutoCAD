"""The capability manifest for Heron AI's registry (tools/export_capabilities.py, D-122). No AutoCAD."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from autocad_mcp.core.bridge import READS_SINCE
from autocad_mcp.core.registry import mcp
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import register_all

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("export_capabilities", ROOT / "tools" / "export_capabilities.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["export_capabilities"] = module
    spec.loader.exec_module(module)
    return module


exporter = _load()


@pytest.fixture(scope="module")
def registered():
    register_all()
    return {tool.name: tool for tool in asyncio.run(mcp.list_tools())}


@pytest.fixture(scope="module")
def manifest():
    return exporter.build()


@pytest.fixture(scope="module")
def by_name(manifest):
    return {row["name"]: row for row in manifest["tools"]}


# --------------------------------------------------------------------------
# Every tool, and the file is the same every time
# --------------------------------------------------------------------------


def test_every_registered_tool_is_in_the_manifest_once(manifest, registered):
    names = [row["name"] for row in manifest["tools"]]
    assert sorted(names) == sorted(registered)
    assert names == sorted(names), "tools are listed in name order"
    assert manifest["count"] == len(registered)


def test_the_file_is_the_same_every_time_and_has_nothing_from_this_pc(manifest):
    first = exporter.render(manifest)
    assert exporter.render(exporter.build()) == first
    assert first.endswith("}\n") and "\r" not in first
    assert str(ROOT) not in first and str(ROOT).replace("\\", "\\\\") not in first
    assert json.loads(first) == manifest


def test_main_writes_the_file_where_asked(tmp_path, capsys, manifest, monkeypatch):
    monkeypatch.setattr(exporter, "build", lambda: manifest)  # built once already, by the fixture
    out = tmp_path / "sub" / "capabilities.json"
    assert exporter.main(["--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == exporter.render(manifest)
    assert f"{manifest['count']} tools written" in capsys.readouterr().out


def test_it_names_the_server_and_plugin_this_code_builds(manifest):
    from autocad_mcp import __version__

    assert manifest["manifest_version"] == exporter.MANIFEST_VERSION
    assert manifest["server"]["version"] == __version__
    props = (ROOT / "autocad" / "Directory.Build.props").read_text(encoding="utf-8")
    assert manifest["plugin"]["version"] == re.search(r"<Version>([^<]+)</Version>", props).group(1)
    uris = {r["uri"] for r in manifest["server"]["resources"]}
    assert {"autocad://tools", "autocad://tools/find/{phrase}", "autocad://diagnose"} <= uris


# --------------------------------------------------------------------------
# Each tool's padlock, kind, lines and inputs come from the server itself
# --------------------------------------------------------------------------


def test_each_tool_carries_its_own_padlock_and_kind(by_name):
    needs = {"read": [], "view": [], "change": ["Changes"], "publish": ["Changes", "Publish"], "admin": ["Changes", "Admin"]}
    for name, row in by_name.items():
        level = risk_of(name)
        assert row["padlock"] == level.value
        assert row["padlocks_needed"] == needs[level.value]
        assert row["kind"] == {Risk.READ: "read", Risk.VIEW: "view"}.get(level, "change"), name


def test_each_tool_has_its_use_when_lines_and_inputs(by_name, registered):
    for name, row in by_name.items():
        assert row["use_when"], f"{name} has no Use when line"
        assert not any(line.startswith(("Use when", "Don't use when")) for line in row["use_when"] + row["dont_use_when"])
        assert row["inputs"] == registered[name].input_schema
        assert row["summary"] and row["title"]
    assert any("autocad_draw_polyline" in line for line in by_name["autocad_draw_line"]["dont_use_when"])


def test_a_tool_that_only_reads_is_marked_read_only_for_mcp_clients(by_name):
    # A client may let a read-only tool run without asking; a registry may too. So every Read tool
    # says so, except the three that keep something of their own: notes on disk, the chosen AutoCAD,
    # the office layer standard imported into Heron's folder (D-120).
    keeps_its_own = {"autocad_project_notes", "autocad_use_autocad", "autocad_layer_standard"}
    for name, row in by_name.items():
        if row["hints"]["read_only"]:
            assert row["padlock"] in ("read", "view"), f"{name} is read-only but needs a padlock"
        elif row["padlock"] == "read":
            assert name in keeps_its_own, f"{name} only reads but is not marked read-only"


# --------------------------------------------------------------------------
# What each tool needs of the plug-in, read from its code
# --------------------------------------------------------------------------


def test_plugin_operations_are_the_plugins_own(manifest):
    known = set(manifest["plugin"]["operations"])
    assert {"loft", "count_entities", "show", "publish_pdf"} <= known
    for row in manifest["tools"]:
        assert set(row["plugin"]["operations"]) <= known, row["name"]
        assert row["plugin"]["role"] in ("gate", "operations", "when_there")
        if row["plugin"]["role"] == "gate":
            assert row["plugin"]["operations"] == [] and row["plugin"]["version_needed"] is None
        if row["plugin"]["role"] == "operations":
            assert row["plugin"]["version_needed"] == manifest["plugin"]["version"]


def test_known_tools_need_what_their_code_asks_of_the_plugin(by_name):
    loft = by_name["autocad_loft"]["plugin"]
    assert loft["role"] == "operations" and "loft" in loft["operations"]
    assert by_name["autocad_shell_solid"]["plugin"]["operations"] == ["shell"]
    assert by_name["autocad_create_styles"]["plugin"]["operations"] == ["multileader_style", "table_style"]
    line = by_name["autocad_draw_line"]["plugin"]
    assert line == {"role": "gate", "operations": [], "version_needed": None, "runs_other_tools": False}
    listing = by_name["autocad_list_entities"]["plugin"]
    assert listing["role"] == "when_there" and listing["operations"] == ["count_entities"]
    assert listing["faster_from"] == READS_SINCE
    # The block reads came after 1.8.1, in a release not named yet: no "faster from" version (D-127).
    for name, operation in (("autocad_count_blocks", "block_references"), ("autocad_list_blocks", "block_definitions")):
        blocks = by_name[name]["plugin"]
        assert blocks["role"] == "when_there" and blocks["operations"] == [operation], name
        assert "faster_from" not in blocks, name
    # So did the length and text reads (D-134).
    for name, operation in (
        ("autocad_total_length", "entity_lengths"),
        ("autocad_measure", "entity_lengths"),
        ("autocad_count_text", "entity_texts"),
        ("autocad_find_text", "entity_texts"),
    ):
        reads = by_name[name]["plugin"]
        assert reads["role"] == "when_there" and reads["operations"] == [operation], name
        assert "faster_from" not in reads, name
    # And the block attribute reads, the two writing tools' too: their writes stay COM's (D-138).
    for name in ("autocad_extract_attributes", "autocad_export_attribute_sheet", "autocad_set_attributes",
                 "autocad_apply_attribute_sheet"):
        reads = by_name[name]["plugin"]
        assert reads["role"] == "when_there" and reads["operations"] == ["block_attributes"], name
        assert "faster_from" not in reads, name
    # And the standards check's object facts; its layers and the reference stay COM's (D-145).
    standards = by_name["autocad_check_standards"]["plugin"]
    assert standards["role"] == "when_there" and standards["operations"] == ["entity_properties"]
    assert "faster_from" not in standards
    # The layer merge reads and merges through the plug-in when it is there, COM otherwise (D-146).
    merging = by_name["autocad_merge_layers"]["plugin"]
    assert merging["role"] == "when_there" and merging["operations"] == ["layer_objects", "merge_layers"]
    assert merging["version_needed"] is None and "faster_from" not in merging
    assert by_name["autocad_batch_draw"]["plugin"]["role"] == "when_there"  # quiet input when it is there
    assert by_name["autocad_sequence"]["plugin"]["runs_other_tools"] is True
    # A keyword's value is not an operation: saved commands have an action called "show".
    assert by_name["autocad_saved_command"]["plugin"]["operations"] == []


def test_operation_names_are_read_from_the_plugins_list(tmp_path):
    source = tmp_path / "PluginOperations.cs"
    source.write_text('["loft"] = Risk.Change,\n            ["show"] = Risk.View,\n', encoding="utf-8")
    assert exporter.plugin_operations(source) == {"loft": "change", "show": "view"}


# --------------------------------------------------------------------------
# The proof, from docs/NEEDS-CHECKING.md
# --------------------------------------------------------------------------

REGISTER = """\
## Group A - AutoCAD 2027 (this PC)

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| A1 | `autocad_alpha` | works | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): fine |
| A2 | `autocad_beta` then `autocad_alpha` | works | **FAIL then PASS** 2026-10-26: fixed |
| A3 | `autocad_beta` | works | NOT RUN |
| A4 | `autocad_gamma` | works | **FAIL** 2026-10-28, AutoCAD 2027: busy |
| A5 | `autocad_delta` | works, unlike `autocad_alpha` in the result | **FAIL then fixed, re-run NOT RUN** 2026-10-28 |
| A6 | `autocad_render` | works | REMOVED 2026-11-21: `autocad_render` is gone |
| A7 | `autocad_epsilon` | works | **Likely PASS** 2026-10-26: not confirmed |

## Group B - AutoCAD 2025 / 2026 (.NET 8 build)

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| B1 | `autocad_alpha` on 2025 | works | NO MACHINE |
| B2 | `autocad_eta` | works | **PASS** 2026-11-01 |

## Server items not provable offline

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| SV1 | `autocad_zeta` | works | **PASS** 2026-11-01 |
"""


def test_a_result_cell_is_read_the_registers_way():
    assert exporter.row_state("**PASS** 2026-10-26, AutoCAD 2027") == "PASS"
    assert exporter.row_state("**FAIL then PASS** 2026-10-26") == "PASS"
    assert exporter.row_state("**FAIL then fixed, re-run NOT RUN** 2026-10-28") == "NOT RUN"
    assert exporter.row_state("**FAIL** 2026-10-28") == "FAIL"
    assert exporter.row_state("NOT RUN — needs an eye") == "NOT RUN"
    assert exporter.row_state("NO MACHINE") == "NO MACHINE"
    assert exporter.row_state("**Likely PASS** 2026-10-26") == "UNCLEAR"
    assert exporter.row_state("REMOVED 2026-11-21") is None


def test_rows_name_tools_in_their_do_and_pass_cells_only():
    rows = {row["row"]: row for row in exporter.register_rows(REGISTER)}
    assert "A6" not in rows  # a removed row is left out
    assert rows["A2"]["tools"] == ["autocad_alpha", "autocad_beta"]
    assert rows["A5"]["tools"] == ["autocad_alpha", "autocad_delta"]
    assert rows["A1"]["passed_in"] == ["2027"]
    assert rows["A2"]["passed_in"] == ["2027"]  # no version in the cell: the group's
    assert rows["B2"]["passed_in"] == ["2025"]
    assert rows["SV1"]["passed_in"] == []  # neither says one
    assert rows["B1"]["state"] == "NO MACHINE"


def test_a_tools_proof_state_is_never_better_than_its_rows():
    tools = ["autocad_alpha", "autocad_beta", "autocad_gamma", "autocad_delta", "autocad_epsilon",
             "autocad_zeta", "autocad_omega"]  # fmt: skip
    proof = exporter.proof_by_tool(REGISTER, tools)
    assert proof["autocad_zeta"]["state"] == "PASS"
    assert proof["autocad_beta"]["state"] == "PARTLY"
    assert proof["autocad_alpha"]["state"] == "PARTLY"  # A1, A2 passed; A5 and B1 not
    assert proof["autocad_alpha"]["passed_in"] == ["2027"]
    assert proof["autocad_gamma"]["state"] == "FAIL"
    assert proof["autocad_delta"]["state"] == "NOT RUN"
    assert proof["autocad_epsilon"]["state"] == "NOT RUN"  # "Likely PASS" is not a pass
    assert proof["autocad_omega"] == {"state": "NO ROW", "rows": [], "passed_in": []}
    assert [r["row"] for r in proof["autocad_beta"]["rows"]] == ["A2", "A3"]


def test_the_real_registers_proof_adds_up(manifest):
    counts = manifest["proof"]["counts"]
    assert set(counts) == set(exporter.PROOF_STATES)
    assert sum(counts.values()) == manifest["count"]
    for row in manifest["tools"]:
        proof = row["proof"]
        if proof["state"] in ("PASS", "PARTLY"):
            assert proof["passed_in"], row["name"]
        if proof["state"] == "NO ROW":
            assert proof["rows"] == []
        else:
            assert proof["rows"], row["name"]
