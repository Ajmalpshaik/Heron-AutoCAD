#!/usr/bin/env python3
"""End-to-end check of autocad-mcp against a real AutoCAD instance.

Every tool is exercised the way an agent would call it. The test works inside a
NEW drawing it creates for itself, so nothing it does can touch a drawing the
user already has open. Leave the drawing unsaved and close it afterwards.

    .venv\\Scripts\\python.exe tools/smoke_test.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from autocad_mcp.core.answers import body  # noqa: E402
from autocad_mcp.tools import (  # noqa: E402
    advanced,
    batch,
    document,
    draw,
    layers,
    modify,
    query,
)

PASS = "  PASS"
FAIL = "  FAIL"

results: list[tuple[bool, str]] = []


def report(ok: bool, label: str, detail: str = "") -> None:
    results.append((ok, label))
    print(f"{PASS if ok else FAIL}  {label}" + (f"  — {detail}" if detail else ""))


def parse(raw: str) -> dict[str, Any]:
    """Tool results are JSON on success and 'Error: ...' text on failure.

    A change job's answer starts with one plain line (DONE, REFUSED, ...: D-62): it is dropped here.
    """
    raw = body(raw)
    if raw.startswith("Error:"):
        raise AssertionError(raw)
    return json.loads(raw)


async def main() -> int:
    print("autocad-mcp smoke test\n" + "=" * 60)

    # --- connection -------------------------------------------------------
    try:
        status = parse(await document.autocad_status())
        active = status.get("active_drawing") or {}
        report(
            status["connected"],
            "autocad_status",
            f"{status['application']} | {active.get('name', 'no drawing')}",
        )
    except AssertionError as exc:
        report(False, "autocad_status", str(exc))
        print("\nCannot continue without a connection. Is AutoCAD running?")
        return 1

    # --- work in a scratch drawing ---------------------------------------
    created = parse(await document.autocad_create_drawing())
    report(created["created"], "autocad_create_drawing", f"{created['name']} ({created['units']})")

    parse(await document.autocad_set_variable(name="INSUNITS", value="4"))
    report(True, "autocad_set_variable", "INSUNITS -> millimeters")

    var = parse(await document.autocad_get_variable(name="INSUNITS"))
    report(var["value"] == 4, "autocad_get_variable", f"INSUNITS={var['value']}")

    # --- layers -----------------------------------------------------------
    layer = parse(
        await layers.autocad_create_layer(
            name="MCP-TEST", color="red", linetype="HIDDEN", make_current=False
        )
    )
    report(layer["name"] == "MCP-TEST", "autocad_create_layer", f"color={layer['color']}")

    listed = parse(await layers.autocad_list_layers(include_entity_counts=False))
    report(
        any(item["name"] == "MCP-TEST" for item in listed["layers"]),
        "autocad_list_layers",
        f"{listed['count']} layers",
    )

    # --- drawing ----------------------------------------------------------
    rect = parse(
        await draw.autocad_draw_rectangle(
            corner1=[0, 0], corner2=[5000, 3000], layer="MCP-TEST"
        )
    )
    report(rect["area"] == 15_000_000, "autocad_draw_rectangle", f"area={rect['area']}")

    line = parse(
        await draw.autocad_draw_line(start=[0, 0], end=[3000, 4000], layer="MCP-TEST")
    )
    report(line["length"] == 5000.0, "autocad_draw_line", f"3-4-5 triangle: {line['length']}")

    circle = parse(
        await draw.autocad_draw_circle(center=[2500, 1500], diameter=1000, layer="MCP-TEST")
    )
    report(circle["radius"] == 500.0, "autocad_draw_circle", "diameter 1000 -> radius 500")

    arc = parse(
        await draw.autocad_draw_arc(
            center=[0, 0], radius=1000, start_angle=0, end_angle=90, layer="MCP-TEST"
        )
    )
    report(
        abs(arc["arc_length"] - 1570.796327) < 0.001,
        "autocad_draw_arc",
        f"quarter circle r=1000: {arc['arc_length']}",
    )

    poly = parse(
        await draw.autocad_draw_polyline(
            points=[[0, 0], [1000, 0], [1000, 1000], [0, 1000]],
            closed=True,
            layer="MCP-TEST",
        )
    )
    report(poly["area"] == 1_000_000, "autocad_draw_polyline", f"closed, area={poly['area']}")

    text = parse(
        await draw.autocad_add_text(
            text="MCP SMOKE TEST", position=[0, 3500], height=200, layer="MCP-TEST"
        )
    )
    report(text["created"], "autocad_add_text", text["handle"])

    mtext = parse(
        await draw.autocad_add_mtext(
            text=r"Line one\PLine two", position=[0, 4200], width=3000, height=150,
            layer="MCP-TEST",
        )
    )
    report(mtext["created"], "autocad_add_mtext", mtext["handle"])

    dim = parse(
        await draw.autocad_add_dimension(
            dimension_type="horizontal",
            point1=[0, 0],
            point2=[5000, 0],
            text_position=[2500, -600],
            layer="MCP-TEST",
        )
    )
    report(dim["measurement"] == 5000.0, "autocad_add_dimension", f"measured {dim['measurement']}")

    hatch = parse(
        await draw.autocad_add_hatch(
            boundary_handles=[poly["handle"]], pattern="ANSI31", scale=20, layer="MCP-TEST"
        )
    )
    report(hatch["created"], "autocad_add_hatch", f"area={hatch.get('area')}")

    ellipse = parse(
        await draw.autocad_draw_ellipse(
            center=[6000, 1500], major_radius=800, minor_radius=400, layer="MCP-TEST"
        )
    )
    report(ellipse["created"], "autocad_draw_ellipse", ellipse["handle"])

    pt = parse(await draw.autocad_draw_point(position=[100, 100], layer="MCP-TEST"))
    report(pt["created"], "autocad_draw_point", pt["handle"])

    # --- querying ---------------------------------------------------------
    summary = parse(await query.autocad_list_entities(summary_only=True))
    report(
        summary["total_matching"] >= 10,
        "autocad_list_entities (summary)",
        f"{summary['total_matching']} entities: {summary['by_type']}",
    )

    circles = parse(await query.autocad_list_entities(entity_type="circle", layer="MCP-TEST"))
    report(circles["total_matching"] == 1, "autocad_list_entities (filtered)", "1 circle")

    entity = parse(await query.autocad_get_entity(handle=circle["handle"]))
    report(
        entity["radius"] == 500.0 and "bounding_box" in entity,
        "autocad_get_entity",
        f"r={entity['radius']}, bbox width={entity['size']['width']}",
    )

    found = parse(await query.autocad_find_text(query="SMOKE"))
    report(found["count"] >= 1, "autocad_find_text", f"{found['count']} match(es)")

    extents = parse(await query.autocad_get_extents())
    report(extents["width"] > 0, "autocad_get_extents", f"{extents['width']} x {extents['height']}")

    dist = parse(await query.autocad_measure(point1=[0, 0], point2=[3000, 4000]))
    report(dist["distance"] == 5000.0, "autocad_measure (distance)", f"{dist['distance']} @ {dist['angle_degrees']}deg")

    totals = parse(await query.autocad_measure(layer="MCP-TEST"))
    report(
        totals["entity_count"] >= 10,
        "autocad_measure (totals)",
        f"{totals['entity_count']} entities, length={totals['total_length']}",
    )

    sel = parse(await query.autocad_get_selection())
    report(isinstance(sel["count"], int), "autocad_get_selection", f"{sel['count']} selected")

    blocks = parse(await layers.autocad_list_blocks(include_unused=True))
    report(isinstance(blocks["count"], int), "autocad_list_blocks", f"{blocks['count']} blocks")

    styles = parse(await layers.autocad_list_styles())
    report(len(styles["text_styles"]) >= 1, "autocad_list_styles", f"{len(styles['text_styles'])} text styles")

    # --- modifying --------------------------------------------------------
    moved = parse(
        await modify.autocad_move_entities(handles=[pt["handle"]], displacement=[500, 500])
    )
    report(moved["moved"] == 1, "autocad_move_entities", str(moved["displacement"]))

    copied = parse(
        await modify.autocad_copy_entities(
            handles=[circle["handle"]], displacement=[0, -2000], count=2
        )
    )
    report(copied["copied"] == 2, "autocad_copy_entities", f"{copied['copied']} copies")

    rotated = parse(
        await modify.autocad_rotate_entities(
            handles=[line["handle"]], base_point=[0, 0], angle=45
        )
    )
    report(rotated["rotated"] == 1, "autocad_rotate_entities", "45 deg")

    scaled = parse(
        await modify.autocad_scale_entities(
            handles=[ellipse["handle"]], base_point=[6000, 1500], factor=0.5
        )
    )
    report(scaled["scaled"] == 1, "autocad_scale_entities", "0.5x")

    mirrored = parse(
        await modify.autocad_mirror_entities(
            handles=[arc["handle"]], axis_point1=[0, 0], axis_point2=[0, 1000]
        )
    )
    report(mirrored["mirrored"] == 1, "autocad_mirror_entities", mirrored["new_handles"][0])

    offset = parse(
        await modify.autocad_offset_entities(handles=[poly["handle"]], distance=-100)
    )
    report(offset["offset"] >= 1, "autocad_offset_entities", f"{offset['offset']} new curve(s)")

    arrayed = parse(
        await modify.autocad_array_entities(
            handles=[pt["handle"]], pattern="rectangular",
            rows=2, columns=3, row_spacing=300, column_spacing=300,
        )
    )
    report(arrayed["arrayed"] >= 5, "autocad_array_entities", f"{arrayed['arrayed']} items")

    modified = parse(
        await modify.autocad_modify_entity(
            handles=[text["handle"]], text="MCP SMOKE TEST - EDITED", color="green"
        )
    )
    report(
        modified["modified"] == 1 and "text" in modified["applied"],
        "autocad_modify_entity",
        f"applied {modified['applied']}",
    )

    verify = parse(await query.autocad_get_entity(handle=text["handle"]))
    report(
        verify["text"] == "MCP SMOKE TEST - EDITED" and verify["color"] == 3,
        "  ^ verified in drawing",
        f"text='{verify['text']}' color={verify['color']}",
    )

    # --- batch (AutoLISP entmake path) ------------------------------------
    grid = []
    for i in range(20):
        grid.append({"type": "line", "start": [i * 100, 10000],
                     "end": [i * 100, 12000], "layer": "MCP-BATCH"})
        grid.append({"type": "line", "start": [0, 10000 + i * 100],
                     "end": [1900, 10000 + i * 100], "layer": "MCP-BATCH"})
    batched = parse(await batch.autocad_batch_draw(operations=grid))
    report(
        batched["created"] == 40 and batched["failed"] == 0 and batched["completed"],
        "autocad_batch_draw",
        f"40 lines in {batched['elapsed_seconds']}s "
        f"({batched.get('entities_per_second')}/s)",
    )
    report(
        len(batched["handles"]) == 40,
        "  ^ handles returned",
        f"first={batched['handles'][0]}",
    )

    probe = parse(await query.autocad_get_entity(handle=batched["handles"][0]))
    report(
        probe["type"] == "line" and probe["layer"] == "MCP-BATCH",
        "  ^ batch handles resolve",
        f"{probe['type']} on {probe['layer']}",
    )

    mixed = parse(await batch.autocad_batch_draw(operations=[
        {"type": "rectangle", "corner1": [3000, 10000], "corner2": [5000, 11000],
         "layer": "MCP-BATCH", "color": "green"},
        {"type": "circle", "center": [4000, 10500], "diameter": 600,
         "layer": "MCP-BATCH"},
        {"type": "text", "position": [3000, 11200], "text": 'PIPE 5" NB',
         "height": 150, "layer": "MCP-BATCH"},
    ]))
    report(
        mixed["created"] == 3 and mixed["failed"] == 0,
        "autocad_batch_draw (mixed types)",
        "rectangle + circle + quoted text",
    )

    quoted = parse(await query.autocad_get_entity(handle=mixed["handles"][2]))
    report(
        quoted["text"] == 'PIPE 5" NB',
        "  ^ LISP string escaping",
        f"text={quoted['text']!r}",
    )

    no_handles = parse(await batch.autocad_batch_draw(
        operations=[{"type": "point", "position": [i * 50, 13000],
                     "layer": "MCP-BATCH"} for i in range(10)],
        return_handles=False,
    ))
    report(
        no_handles["created"] == 10 and no_handles["handles"] == [],
        "autocad_batch_draw (return_handles=false)",
        f"{no_handles['created']} created, no handles returned",
    )

    bad_batch = body(await batch.autocad_batch_draw(operations=[
        {"type": "line", "start": [0, 0], "end": [1, 1]},
        {"type": "banana"},
    ]))
    report(
        bad_batch.startswith("Error:") and "Operation 1" in bad_batch,
        "guard: batch names the bad operation",
        bad_batch[:70],
    )

    # A whole batch must reverse with one Ctrl+Z, not one press per entity.
    # Counts come from autocad_status, which reads ModelSpace.Count directly —
    # the query tools would each add their own undo step (AutoCAD charges one
    # for any selection), which would consume the UNDO being tested.
    async def entity_count() -> int:
        status = parse(await document.autocad_status())
        return status["active_drawing"]["model_space_entities"]

    before_undo = await entity_count()
    undo_batch = parse(await batch.autocad_batch_draw(operations=[
        {"type": "line", "start": [i * 20, 15000], "end": [i * 20, 15500],
         "layer": "MCP-UNDO"} for i in range(15)
    ], return_handles=False))
    after_undo = await entity_count()
    parse(await advanced.autocad_send_command(command="_.UNDO\n1\n"))
    restored = await entity_count()
    report(
        undo_batch["created"] == 15
        and after_undo == before_undo + 15
        and restored == before_undo,
        "batch is one undo step",
        f"{before_undo} -> {after_undo} -> {restored} after a single UNDO",
    )

    # --- advanced ---------------------------------------------------------
    lisp = parse(await advanced.autocad_run_lisp(expression='(getvar "INSUNITS")'))
    report(lisp["result"] == "4", "autocad_run_lisp", f"returned '{lisp['result']}'")

    lisp2 = parse(
        await advanced.autocad_run_lisp(
            expression='(sslength (ssget "_X" (list (cons 8 "MCP-TEST"))))'
        )
    )
    report(not lisp2["timed_out"], "autocad_run_lisp (ssget)", f"MCP-TEST holds {lisp2['result']}")

    cmd = parse(await advanced.autocad_send_command(command="_.CIRCLE\n9000,0\n250\n"))
    report(cmd["completed"], "autocad_send_command", "drew a circle via command line")

    regen = parse(await advanced.autocad_regen())
    report(regen["regenerated"] == "active", "autocad_regen")

    zoom = parse(await document.autocad_zoom(mode="extents"))
    report(zoom["zoomed"] == "extents", "autocad_zoom")

    # --- guard rails: these must FAIL cleanly, not crash ------------------
    bad_dialog = body(await advanced.autocad_send_command(command="PURGE"))
    report(
        bad_dialog.startswith("Error:") and "-PURGE" in bad_dialog,
        "guard: dialog command refused",
        bad_dialog[:70],
    )

    bad_lisp = body(await advanced.autocad_run_lisp(expression='(getvar "INSUNITS"'))
    report(
        bad_lisp.startswith("Error:") and "arenthes" in bad_lisp,
        "guard: unbalanced parens refused",
        bad_lisp[:70],
    )

    bad_handle = body(await query.autocad_get_entity(handle="ZZZZZZ"))
    report(bad_handle.startswith("Error:"), "guard: bad handle refused", bad_handle[:70])

    bad_circle = body(await draw.autocad_draw_circle(center=[0, 0], radius=10, diameter=20))
    report(
        bad_circle.startswith("Error:") and "only one" in bad_circle,
        "guard: radius+diameter refused",
        bad_circle[:70],
    )

    unconfirmed = parse(
        await modify.autocad_delete_entities(handles=[pt["handle"]], confirm=False)
    )
    report(
        unconfirmed["deleted"] == 0 and unconfirmed["would_delete"] == 1,
        "guard: delete needs confirm",
        "previewed without deleting",
    )

    # --- cleanup ----------------------------------------------------------
    deleted = parse(
        await modify.autocad_delete_entities(handles=[pt["handle"]], confirm=True)
    )
    report(deleted["deleted"] == 1, "autocad_delete_entities", "confirmed delete works")

    # --- summary ----------------------------------------------------------
    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    print("=" * 60)
    print(f"{passed}/{total} checks passed")
    if passed < total:
        print("\nFailed:")
        for ok, label in results:
            if not ok:
                print(f"  - {label}")
        return 1
    print("\nThe scratch drawing is still open in AutoCAD; close it without saving.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
