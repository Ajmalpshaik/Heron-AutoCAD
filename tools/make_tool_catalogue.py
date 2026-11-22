"""Write docs/TOOL-CATALOGUE.md: every tool in plain words, made from the live registry.

    python tools/make_tool_catalogue.py            # rewrite docs/TOOL-CATALOGUE.md
    python tools/make_tool_catalogue.py --check    # exit 1 if the file on disk is stale

Needs no AutoCAD and changes only that one file. Nothing in the catalogue is typed by hand
except the group names, the Heron-tab buttons and the fixed sentences in this script: everything
about a tool comes from the code, so the page cannot drift from it (tests/test_tool_catalogue.py
fails when a tool is missing or the file is stale):

* the **name, purpose, Use when / Don't use when lines, inputs, Returns and Error Handling** come
  from each tool's own docstring and input schema (the live registry);
* the **padlock** comes from ``core/risk.py``;
* **what the tool needs of the plug-in** and its **live-proof state** come from the same code that
  writes ``dist/capabilities.json`` (``tools/export_capabilities.py``, #75), i.e. from
  ``docs/NEEDS-CHECKING.md``.

The file is the same every time for the same code: sorted, no date, no path from this PC.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import inspect
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "TOOL-CATALOGUE.md"

# --------------------------------------------------------------------------
# The groups. A tool belongs to exactly one; a new tool must be added here
# (the test and this script both fail on a tool no group names).
# --------------------------------------------------------------------------

GROUPS: list[tuple[str, str, str]] = [
    ("drawing", "Drawing and coordinates", "Lines, circles, polylines, hatches, standard shapes, and the coordinate system they are drawn in."),
    ("editing", "Editing and reading objects", "Move, copy, trim, fillet, change properties, and the tools that find and measure what is drawn."),
    ("text", "Text, labels and tables", "Text, leaders, labels, tags, schedules as tables, text styles and annotation scales."),
    ("dimensions", "Dimensions", "Dimensions, dimension runs, centre marks."),
    ("blocks", "Blocks, attributes and references", "Blocks and their attributes, dynamic blocks, xrefs, underlays, taking objects from another drawing."),
    ("layers", "Layers and linetypes", "Layers, layer states, the office layer standard, linetypes."),
    ("sheets", "Sheets and printing", "Layouts, viewports, title blocks, drawing lists, page set-up, PDF."),
    ("solids", "3D, lights and rendering set-up", "Solids, surfaces, meshes, 3D edits, sections, lights, materials, the sun, cameras. Never the render itself."),
    ("checks", "Checks and reports", "Check lists, standards checks, drawing reports, audit and purge."),
    ("files", "Files and drawings", "Open, create, save, export, switch drawing, read a file without AutoCAD."),
    ("heron", "Heron itself, looking, commands and settings", "The connection, what Heron did, undo, saved commands, looking at the drawing, and the Admin tools (commands, AutoLISP, system variables)."),
]

_G = {
    "drawing": """draw_line draw_circle draw_arc draw_ellipse draw_point draw_polyline draw_rectangle draw_spline
        draw_multiline batch_draw make_shape add_hatch add_construction_line add_donut add_region
        add_revision_cloud add_wipeout divide_curve super_hatch trace_boundary import_pdf
        create_hatch_pattern get_ucs set_ucs convert_points drawing_setup""",
    "editing": """move_entities copy_entities rotate_entities scale_entities mirror_entities offset_entities
        array_entities associative_array stretch trim_extend fillet_chamfer break_curve join_curves explode
        delete_entities modify_entity match_properties edit_vertex edit_spline group list_groups draw_order
        overkill tidy_entities hyperlinks list_hyperlinks list_entities get_entity polyline_info
        select_connected get_extents measure total_length""",
    "text": """add_text add_mtext add_label batch_labels add_multileader add_field_label find_text
        find_replace_text text_clean align_text count_text label_segment_lengths number_tags add_table
        set_table_cells table_from_excel update_table_links create_styles list_styles annotation_scales
        list_annotation_scales""",
    "dimensions": "add_dimension dimension_run space_dimensions break_dimensions add_centre_marks",
    "blocks": """make_block insert_block list_blocks count_blocks place_along place_from_csv set_attributes
        extract_attributes sync_attributes export_attribute_sheet apply_attribute_sheet
        get_dynamic_properties set_dynamic_properties attach_xref manage_xref xref_tree attach_underlay
        clip_reference import_from_drawing copy_from_drawing break_at_blocks""",
    "layers": """create_layer delete_layer list_layers set_current_layer set_layer_state layer_states
        isolate_layers merge_layers remap_layers layer_standard create_linetype""",
    "sheets": """create_layout add_viewport manage_layouts list_layouts page_setup place_title_block sheet_set
        publish_pdf save_view list_views""",
    "solids": """add_solid add_pyramid add_polysolid add_surface add_mesh extrude_profile loft solid_boolean
        shell_solid slice_solid section_plane fillet_solid_edges chamfer_solid_edges edit_solid_faces
        press_pull_faces imprint_solid separate_solid thicken_surface transform_3d draw_3d_path
        list_solid_faces_and_edges solid_properties check_interference flatten_views set_3d_view
        add_camera_view add_light list_lights switch_lights set_sun set_render_exposure create_material
        list_materials apply_material geo_location get_geo_location""",
    "checks": """checklist checklist_report share_checklist check_standards check_folder drawing_report audit
        purge""",
    "files": """create_drawing open_drawing save_drawing switch_drawing list_drawings export etransmit
        read_file""",
    "heron": """status why gaps activity undo_last use_autocad companion project_notes saved_command sequence
        show preview zoom regen tiled_viewports get_selection get_variable set_variable run_lisp
        send_command""",
}
GROUP_OF: dict[str, str] = {}
for _key, _names in _G.items():
    for _short in _names.split():
        GROUP_OF["autocad_" + _short] = _key

# The few tools that have a button (or a window) on the Heron tab. There is no button per tool.
HERON_TAB: dict[str, str] = {
    "autocad_status": "**Heron tab > Heron > Bridge Status** shows whether Heron is connected to this AutoCAD, and the padlocks. It is a window for you; this tool is the same check for Claude.",
    "autocad_activity": "**Heron tab > Heron > Heron palette > Activity** lists the same changes, newest first, with Select, Zoom and Undo where they can act.",
    "autocad_undo_last": "**Heron tab > Heron > Heron palette > Activity**, the Undo button beside a change, does the same for that change.",
    "autocad_saved_command": "**Heron tab > Heron > Heron palette > Saved commands** lists the commands saved with this tool.",
    "autocad_show": "**Heron tab > Heron > Heron palette > Activity**: Select and Zoom beside a change do the same for that change.",
    "autocad_use_autocad": "**Heron tab > Heron > Free this AutoCAD** lets another chat use this AutoCAD at once.",
}

# Why a padlock is named the way it is, for the "Where to find it" line.
PADLOCK_LINE = {
    "read": "No padlock needed: it only reads the drawing. Heron must be pressed (connected).",
    "view": "No padlock needed: it changes only what is on your screen, never the drawing. Heron must be pressed (connected).",
    "change": "Needs the **Changes** padlock ON (Heron tab > Settings > Changes).",
    "publish": "Needs the **Changes** and **Publish** padlocks ON (Heron tab > Settings).",
    "admin": "Needs the **Changes** and **Admin** padlocks ON (Heron tab > Settings).",
}

_SECTION = re.compile(r"^(Args|Arguments|Returns|Examples|Error Handling|Raises|Note|Notes):\s*$", re.M)
_QUOTED = re.compile(r"\"([^\"]{8,200})\"")


def _load_exporter() -> Any:
    spec = importlib.util.spec_from_file_location("export_capabilities", ROOT / "tools" / "export_capabilities.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["export_capabilities"] = module
    spec.loader.exec_module(module)
    return module


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _cut(text: str, limit: int) -> str:
    """Cut at the last sentence end (or, failing that, word end) before ``limit``."""
    text = _flat(text)
    if len(text) <= limit:
        return text
    head = text[:limit]
    stop = max(head.rfind(". "), head.rfind("; "))
    if stop > limit // 2:
        return head[: stop + 1]
    return head[: head.rfind(" ")].rstrip(",;:") + " ..."


def _sections(description: str) -> tuple[str, dict[str, str]]:
    """The cleaned body, and each docstring section (Args, Returns, Examples, Error Handling) by name."""
    text = inspect.cleandoc(description)
    parts = _SECTION.split(text)
    body = parts[0]
    found = {parts[i]: inspect.cleandoc(parts[i + 1]) for i in range(1, len(parts) - 1, 2)}
    return body, found


def _body_paragraph(body: str) -> str:
    paragraphs = [p for p in re.split(r"\n\s*\n", body.strip())[1:] if p.strip()]
    return _cut(" ".join(paragraphs[:2]), 520) if paragraphs else ""


def _sample_request(row: dict[str, Any]) -> str:
    for line in row["use_when"]:
        found = _QUOTED.search(line)
        if found:
            return found.group(1).strip()
    return row["summary"]


def _no_autocad(description: str) -> bool:
    return bool(re.search(r"works with autocad closed|needs no autocad|answers even with autocad closed|autocad is closed", description, re.I))


def _sentence(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:]


def _param_line(name: str, spec: dict[str, Any]) -> str:
    text = _cut(spec.get("description", ""), 150)
    return f"`{name}`" + (f": {text}" if text else "")


def _inputs(schema: dict[str, Any]) -> list[str]:
    properties = {k: v for k, v in (schema.get("properties") or {}).items() if k != "dry_run"}
    required = [k for k in schema.get("required", []) if k in properties]
    optional = [k for k in properties if k not in required]
    lines: list[str] = []
    if not properties:
        return ["Nothing: it takes no inputs."]
    for name in required:
        lines.append("Needs " + _param_line(name, properties[name]))
    if optional:
        shown = optional[:10]
        more = f", and {len(optional) - len(shown)} more" if len(optional) > len(shown) else ""
        lines.append("Optional: " + ", ".join(f"`{n}`" for n in shown) + more + ".")
    return lines


def _proof_text(row: dict[str, Any]) -> str:
    proof = row["proof"]
    rows = ", ".join(r["row"] for r in proof["rows"])
    state = proof["state"]
    if state == "PASS":
        return f"**PASS** in AutoCAD {', '.join(proof['passed_in']) or '(version not recorded)'} (rows {rows})."
    if state == "PARTLY":
        passed = ", ".join(r["row"] for r in proof["rows"] if r["state"] == "PASS")
        return f"**PARTLY**: rows {passed} passed in AutoCAD {', '.join(proof['passed_in']) or '?'}; the rest are NOT RUN (rows {rows})."
    if state == "FAIL":
        return f"**FAIL**: a live row failed and has not passed since (rows {rows}). Do not rely on it."
    if state == "NOT RUN":
        return f"**NOT RUN**: built and tested offline, never run in AutoCAD (rows {rows})."
    return "**NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD."


def _plugin_text(row: dict[str, Any]) -> str:
    plugin = row["plugin"]
    if plugin["role"] == "operations":
        ops = ", ".join(f"`{o}`" for o in plugin["operations"]) or "its own steps"
        return (
            f"The plug-in does part of the work ({ops}); it needs plug-in **{plugin['version_needed']}** or newer. "
            "An older plug-in refuses it and nothing is sent."
        )
    if plugin["role"] == "when_there":
        extra = f" (from plug-in {plugin['faster_from']})" if plugin.get("faster_from") else ""
        return f"Uses the plug-in for speed when it can{extra}; otherwise it does the same job over COM."
    return "The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM."


def tool_section(row: dict[str, Any], description: str) -> list[str]:
    name = row["name"]
    body, parts = _sections(description)
    level = row["padlock"]
    sample = _sample_request(row)
    lines = [f"### `{name}`", "", f"**What it does.** {row['summary']}"]
    paragraph = _body_paragraph(body)
    if paragraph:
        lines.append(f"{paragraph}")
    lines += ["", "**The problem it solves.**"]
    solves = row["use_when"][:4] or [row["summary"]]
    lines += [f"- {_sentence(_cut(line, 260))}" for line in solves]
    for avoid in row["dont_use_when"][:3]:
        lines.append(f"- *Not for:* {_cut(avoid, 240)}")

    no_acad = _no_autocad(description)
    where = PADLOCK_LINE[level]
    if no_acad and level in ("read", "view"):
        where = "No padlock needed, and it answers even with AutoCAD closed."
    lines += ["", "**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. " + where]
    if name in HERON_TAB:
        lines.append(f"On the Heron tab: {HERON_TAB[name]}")

    steps = ["Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange."]
    if no_acad and level in ("read", "view"):
        steps = ["Nothing to prepare: AutoCAD may be closed. (With AutoCAD open, the drawing it names is the one Heron reads.)"]
    if level in ("change", "publish", "admin"):
        padlocks = " and ".join(f"**{p}**" for p in row["padlocks_needed"])
        steps.append(f"In **Settings**, turn {padlocks} ON (each asks first). They are all OFF when AutoCAD starts.")
    steps.append(f"Ask Claude, for example: *\"{sample}\"*")
    if level in ("change", "publish", "admin"):
        steps.append("Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.")
    else:
        steps.append("Read the answer Claude gives back.")
    lines += ["", "**How to use it.**"] + [f"{i}. {s}" for i, s in enumerate(steps, 1)]

    lines += ["", "**What it needs from you.**"] + [f"- {x}" for x in _inputs(row["inputs"])]

    returns = parts.get("Returns", "")
    result: list[str] = []
    if level in ("change", "publish", "admin"):
        result.append("One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.")
        if not row["hints"]["read_only"]:
            result.append("It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark." if level == "change" else "A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.")
    else:
        result.append("Claude reads the answer back to you in words; nothing in the drawing changes.")
    if returns:
        shape = re.sub(r"^str:\s*", "", _flat(returns))
        result.append(f"Technical shape of the answer: `{_cut(shape, 240)}`")
    lines += ["", "**The result to expect.**"] + [f"- {r}" for r in result]

    limits: list[str] = []
    for item in re.findall(r"^- (.+?)(?=^- |\Z)", parts.get("Error Handling", ""), re.M | re.S)[:3]:
        limits.append(_cut(item, 240))
    limits.append(_plugin_text(row))
    lines += ["", "**Limits and versions.**"] + [f"- {x}" for x in limits]
    lines += ["", f"**Live proof.** {_proof_text(row)}", ""]
    return lines


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------


async def _gather() -> tuple[dict[str, Any], dict[str, str]]:
    exporter = _load_exporter()
    exporter._prepare_imports()
    manifest = await exporter._manifest()
    from autocad_mcp.core.registry import mcp

    descriptions = {t.name: t.description or "" for t in await mcp.list_tools()}
    return manifest, descriptions


def missing_from(text: str, names: list[str]) -> list[str]:
    """The tools whose section heading is not in the catalogue text."""
    return [n for n in names if f"### `{n}`" not in text]


def build(manifest: dict[str, Any], descriptions: dict[str, str]) -> str:
    rows = {r["name"]: r for r in manifest["tools"]}
    unassigned = sorted(set(rows) - set(GROUP_OF))
    unknown = sorted(set(GROUP_OF) - set(rows))
    if unassigned or unknown:
        raise SystemExit(
            "tools/make_tool_catalogue.py: add each new tool to a group in _G "
            f"(not in any group: {unassigned or 'none'}; named but not registered: {unknown or 'none'})."
        )
    total = len(rows)
    states = {s: sum(1 for r in rows.values() if r["proof"]["state"] == s) for s in ("PASS", "PARTLY", "NOT RUN", "FAIL", "NO ROW")}
    out: list[str] = [
        "# Tool catalogue",
        "",
        "<!-- Made by tools/make_tool_catalogue.py from the live tool list. Do not edit by hand: "
        "run `python tools/make_tool_catalogue.py` instead. tests/test_tool_catalogue.py fails when this file is stale. -->",
        "",
        f"Every one of Heron's **{total}** tools, in plain words, grouped by the job it does. For each tool: what it does, "
        "the problem it solves, where to find it, how to use it step by step, what it needs from you, the result to "
        "expect, its limits, and whether anyone has seen it work in a real AutoCAD.",
        "",
        "> **Read this first.** Nothing here claims a tool works in AutoCAD. The *Live proof* line of each tool is copied "
        "from [NEEDS-CHECKING](NEEDS-CHECKING.md), the one register of what was run for real. "
        f"Today: **{states['PASS']}** tools PASS, **{states['PARTLY']}** PARTLY, **{states['NOT RUN']}** NOT RUN, "
        f"**{states['FAIL']}** FAIL, **{states['NO ROW']}** have no row at all. A PASS means a real AutoCAD, "
        "in the version named, gave the result the row expects; a build or an offline test is not a proof.",
        "",
        "## How Heron's tools work (the same for every tool)",
        "",
        "- **You do not click a tool.** There is no ribbon button per tool. You describe the job to Claude in the chat; "
        "Claude picks the tool. The Heron tab only holds the connection and the padlocks "
        "([06 - the plug-in](06-heron-plugin.md)).",
        "- **Heron must be pressed first.** AutoCAD starts disconnected. Press **Heron** on the Heron tab (or type "
        "`HERON`): the heron turns orange. Until then every tool is refused with the sentence that says so.",
        "- **Padlocks decide what is allowed, and all start OFF** (in **Settings**; each asks before it turns on):",
        "",
        "| Level | Padlocks that must be ON | What it covers |",
        "|---|---|---|",
    ]
    for key, words in (("read", "none: reads the drawing"), ("view", "none: changes only the screen"), ("change", "Changes"), ("publish", "Changes + Publish"), ("admin", "Changes + Admin")):
        count = sum(1 for r in rows.values() if r["padlock"] == key)
        cover = {
            "read": "looking, listing, measuring, checking",
            "view": "zoom, switch or open a drawing, 3D view direction",
            "change": "drawing, editing, text, blocks, layers, sheets, 3D",
            "publish": "saving, exporting, plotting, reports written to files",
            "admin": "commands, AutoLISP, system variables, purge, audit",
        }[key]
        out.append(f"| {key.capitalize()} ({count} tools) | {words} | {cover} |")
    out += [
        "",
        "- **Every change answers with one line first**: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Every change is one undo step.",
        "- **Coordinates are in the drawing's own units**, and angles are degrees. Claude checks the units first with `autocad_status`.",
        "- **AutoCAD versions.** The plug-in is built for AutoCAD **2021 to 2027** (full AutoCAD, not LT): 2021-2024 on .NET Framework 4.8, "
        "2025-2026 on .NET 8, 2027 on .NET 10. It has only ever been run in **2027**, and only the rows marked PASS in "
        "[NEEDS-CHECKING](NEEDS-CHECKING.md). For 2021-2026 nothing was run: groups B and C there are NO MACHINE.",
        "- **A tool Claude cannot find or is refused**: ask Claude `why can't you do this?` (the tool `autocad_why`), which names the "
        "real reason and what you do about it. The longer fixes are in [TROUBLESHOOTING](TROUBLESHOOTING.md).",
        "",
        "## The groups",
        "",
        "| Group | Tools | What is in it |",
        "|---|---|---|",
    ]
    by_group = {key: sorted(n for n, g in GROUP_OF.items() if g == key) for key, _, _ in GROUPS}
    for key, title, about in GROUPS:
        out.append(f"| [{title}](#{_anchor(title)}) | {len(by_group[key])} | {about} |")
    out += ["", "## Every tool at a glance", "", "| Tool | Group | Padlocks | Live proof |", "|---|---|---|---|"]
    title_of = {key: title for key, title, _ in GROUPS}
    for name in sorted(rows):
        row = rows[name]
        words = manifest["padlocks"][row["padlock"]]["words"].replace("none - ", "none: ")
        out.append(f"| [`{name}`](#{name}) | {title_of[GROUP_OF[name]]} | {words} | {row['proof']['state']} |")
    for key, title, about in GROUPS:
        out += ["", f"## {title}", "", about, ""]
        for name in by_group[key]:
            out += tool_section(rows[name], descriptions[name])
    text = "\n".join(out).rstrip() + "\n"
    return text


def _anchor(title: str) -> str:
    return re.sub(r"[^a-z0-9 -]", "", title.lower()).replace(" ", "-")


def generate() -> str:
    manifest, descriptions = asyncio.run(_gather())
    return build(manifest, descriptions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if docs/TOOL-CATALOGUE.md is stale")
    args = parser.parse_args()
    text = generate()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("docs/TOOL-CATALOGUE.md is stale: run python tools/make_tool_catalogue.py", file=sys.stderr)
            return 1
        print("docs/TOOL-CATALOGUE.md is current.")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {OUT.relative_to(ROOT)} ({text.count(chr(10))} lines).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
