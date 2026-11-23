"""Cleaning up an imported drawing, and packing one to send out.

- autocad_overkill: doubled and overlapping lines, arcs and circles (#112, D-84).
- autocad_trace_boundary: a closed outline round a point, by the plug-in's
  Editor.TraceBoundary, never by typing -BOUNDARY or BPOLY (#118, D-84).
- autocad_etransmit: the drawing with its xrefs, images, underlays, fonts and
  plot styles in one folder or zip (#114, D-85).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, StrictInt

from ..acad import overkill as overkill_geometry
from ..acad import transmittal
from ..acad.entities import resolve_handle
from ..core.bridge import OLD_PLUGIN, BridgeRefused
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import AutocadError, com_message, raise_if_busy
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta, undo_mark
from ..core.variants import group_coordinates
from ._shared import (
    COLOR_OPT,
    COORDS_OPT,
    LAYER_OPT,
    SPACE_OPT,
    in_plugin,
    point,
    ucs_for,
    world_coords,
)
from .edit2d import _width, _write_polyline
from .xrefs import _walk, _xref_nodes

# ---- Overkill (#112) ---------------------------------------------------------------

# Read over COM one by one: past this many curves the read alone takes minutes.
MOST_CURVES = 20_000
MOST_SCANNED = 200_000
# What a dry run lists in full; the counts are always whole.
MOST_LISTED = 200

CURVE_KINDS = {
    "AcDbLine": "line",
    "AcDbArc": "arc",
    "AcDbCircle": "circle",
    "AcDbPolyline": "polyline",
    "AcDb2dPolyline": "polyline",
}


def _try(getter, default=None):
    try:
        return getter()
    except BaseException as exc:  # noqa: BLE001 - an absent property is expected here
        raise_if_busy(exc)
        return default


def read_curve(entity: Any) -> dict[str, Any] | None:
    """One line, arc, circle or flat polyline as overkill.plan reads it; None for anything else."""
    kind = CURVE_KINDS.get(str(_try(lambda: entity.ObjectName, "")))
    if kind is None:
        return None
    item: dict[str, Any] = {
        "handle": str(entity.Handle),
        "kind": kind,
        "layer": str(_try(lambda: entity.Layer, "0")),
    }
    if kind == "line":
        item["start"] = [float(v) for v in entity.StartPoint]
        item["end"] = [float(v) for v in entity.EndPoint]
        return item
    normal = _try(lambda: entity.Normal)
    if normal is not None:
        item["normal"] = [float(v) for v in normal]
    if kind in ("arc", "circle"):
        item["centre"] = [float(v) for v in entity.Center]
        item["radius"] = float(entity.Radius)
        if kind == "arc":
            item["start_angle"] = float(entity.StartAngle)
            item["end_angle"] = float(entity.EndAngle)
        return item
    name = str(entity.ObjectName)
    if name == "AcDb2dPolyline":
        item["old_style"] = True
    if name == "AcDb2dPolyline" and int(_try(lambda: entity.Type, 0) or 0) != 0:
        # A curve-fit or spline-fit polyline: its vertices are not its shape.
        item["kind"] = "fitted polyline"
        return item
    stride = 2 if name == "AcDbPolyline" else 3
    vertices = [[p[0], p[1]] for p in group_coordinates(entity.Coordinates, stride)]
    closed = bool(_try(lambda: entity.Closed, False))
    count = len(vertices) if closed else len(vertices) - 1
    item["vertices"] = vertices
    item["bulges"] = [float(entity.GetBulge(i)) for i in range(max(count, 0))]
    item["closed"] = closed
    item["elevation"] = float(_try(lambda: entity.Elevation, 0.0) or 0.0)
    return item


def _curves_in(doc: Any, space: str, layers: list[str] | None, handles: list[str] | None) -> tuple[list[dict[str, Any]], int]:
    """The curves to look at, and how many objects were read to find them."""
    wanted = {name.strip().lower() for name in layers} if layers else None
    container = get_space(doc, space)
    if handles:
        # Only objects in this space: one in another layout, or inside a block
        # definition (every insert would change), is never looked at.
        owner = _try(lambda: container.ObjectID)
        entities = []
        for h in handles:
            entity = resolve_handle(doc, h)
            if owner is not None and _try(lambda e=entity: e.OwnerID) != owner:
                raise AutocadError(
                    f"{entity.Handle} is not in {space} space (it is in another layout or inside a block). "
                    "Give handles from one space only. Nothing was changed."
                )
            entities.append(entity)
    else:
        count = int(container.Count)
        if count > MOST_SCANNED:
            raise AutocadError(
                f"This space holds {count} objects; Heron's overkill reads at most {MOST_SCANNED}. "
                "Give layers=[...] or handles=[...] to look at part of it, or type OVERKILL in AutoCAD."
            )
        entities = (container.Item(i) for i in range(count))
    items: list[dict[str, Any]] = []
    scanned = 0
    for entity in entities:
        scanned += 1
        if str(_try(lambda e=entity: e.ObjectName, "")) not in CURVE_KINDS:
            continue
        if wanted is not None and str(_try(lambda e=entity: e.Layer, "")).strip().lower() not in wanted:
            continue
        item = read_curve(entity)
        if item is None:
            continue
        items.append(item)
        if len(items) > MOST_CURVES:
            raise AutocadError(
                f"More than {MOST_CURVES} lines, arcs and polylines to look at. Give layers=[...] to "
                "do it a few layers at a time, or type OVERKILL in AutoCAD for the whole drawing."
            )
    return items, scanned


def _locked(doc: Any, layer_names: set[str]) -> list[str]:
    locked = []
    for name in sorted(layer_names, key=str.lower):
        layer = _try(lambda n=name: doc.Layers.Item(n))
        if layer is not None and bool(_try(lambda la=layer: la.Lock, False)):
            locked.append(name)
    return locked


def _short(rows: list[dict[str, Any]], most: int = MOST_LISTED) -> list[dict[str, Any]]:
    return rows[:most]


def _fingerprint(found: dict[str, Any]) -> str:
    """A short fingerprint of exactly what would be erased and stretched, to tie confirm to the list shown."""
    shown = {"erase": found["erase"], "change": found["change"]}
    if found.get("rebuild"):
        shown["rebuild"] = found["rebuild"]
    text = json.dumps(shown, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


@mcp.tool(name="autocad_overkill", **tool_meta("Overkill: Delete Duplicate And Overlapping Lines", destructive=True))
@tool_errors
async def autocad_overkill(
    layers: Annotated[list[str] | None, Field(default=None, description="Only look at these layers, e.g. ['A-WALL', 'M-DUCT']. Omit for every layer in the space.")] = None,
    handles: Annotated[list[str] | None, Field(default=None, description="Only look at these objects. Omit to look at the whole space.")] = None,
    tolerance: Annotated[float, Field(default=overkill_geometry.DEFAULT_TOLERANCE, gt=0, le=1000, description="How close two curves must be to count as the same, in drawing units. AutoCAD's OVERKILL uses 0.000001; an import with rounding noise may need 0.01 or more.")] = overkill_geometry.DEFAULT_TOLERANCE,
    ignore_layer: Annotated[bool, Field(default=False, description="true: a line on one layer can be a copy of one on another layer. false (the default): only on the same layer.")] = False,
    join_end_to_end: Annotated[bool, Field(default=False, description="true: lines (and arcs) that only touch end to end in one straight run are joined into one too, as OVERKILL's 'combine co-linear objects when aligned end to end'.")] = False,
    tidy_polylines: Annotated[bool, Field(default=False, description="true: a polyline that goes back over itself, or has zero-length segments, is rebuilt from its own vertices without the doubled stretch, as OVERKILL's 'optimize segments within polylines'. false (the default): polylines are only erased when they are copies, never changed.")] = False,
    space: Annotated[str, SPACE_OPT] = "model",
    confirm: Annotated[bool, Field(default=False, description="false (the default) only lists what would be erased and stretched. true does it, in one undo step, after the modeller has seen the list.")] = False,
    plan_id: Annotated[str | None, Field(default=None, description="With confirm=true: the plan_id the listing call gave. If the drawing changed since, nothing is done and it says so.")] = None,
) -> str:
    """Find and delete doubled and overlapping lines, arcs and circles - AutoCAD's OVERKILL.

    An import from Revit or IFC often draws every wall line twice, or in
    pieces lying over each other. This finds them and says, by handle, what
    would go and why: an exact copy, a line lying inside a longer one, lines
    overlapping on one straight line (merged into the oldest one, which is
    stretched to cover them), arcs on one circle, zero-length lines, a copy
    of a polyline, a loose line lying on a polyline. The oldest object
    (lowest handle) is always the one kept.

    Polylines are never broken: where one overlaps another, or a loose line
    lies only partly on one, it is listed under 'left'. With
    tidy_polylines=true a polyline that goes back over itself (a doubled
    stretch at its end, or a zig-zag along one straight line or circle) or
    has zero-length segments is rebuilt from its own vertices without them
    (listed under 'rebuild' with the segments going); one that goes back
    over itself part way along, which one polyline cannot draw any other
    way, is listed under 'left'.

    The first call changes nothing and gives a plan_id. With confirm=true
    and that plan_id it erases and stretches exactly what was listed (if
    the drawing changed since, nothing is done) in one undo step, and AutoCAD then asks the modeller whether
    to keep the erased objects erased (Heron's erase question): anything
    but "keep them erased" brings them back.

    Args:
        layers (Optional[list[str]]): only these layers.
        handles (Optional[list[str]]): only these objects.
        tolerance (float): how close is the same, in drawing units.
        ignore_layer (bool): compare across layers.
        join_end_to_end (bool): also join lines touching end to end.
        tidy_polylines (bool): also rebuild polylines going back over themselves.
        space (str): 'model' or 'paper'.
        confirm (bool): false lists, true does it.
        plan_id (Optional[str]): the listing's plan_id, needed with confirm.

    Returns:
        str: JSON: {"confirmed": bool, "plan_id": str, "looked_at": int, "erase_count": int,
             "stretch_count": int, "erase": [{"handle", "type", "reason",
             "kept"}], "change": [{"handle", "type", "start", "end" |
             "start_angle", "end_angle", "was", "why"}],
             "rebuild_count": int, "rebuild": [{"handle", "vertices", "bulges",
             "segments_going": [{"segment", "from", "to", "why"}],
             "new_segments", "why"}],
             "left": [{"handles", "why"}], "skipped_count": int}

    Examples:
        - Use when: "the architect's import has doubled lines, clean them up"
          — first call lists them, then confirm=true with its plan_id.
        - Use when: "run overkill on the A-WALL layer" — layers=['A-WALL'].
        - Use when: "delete duplicate lines after the Revit export".
        - Use when: "merge the overlapping duct lines into one".
        - Use when: "the polylines go back over themselves, optimise the
          segments" — tidy_polylines=true.
        - Don't use when: you want to delete objects you already picked -
          autocad_delete_entities.
        - Don't use when: you want overlapping objects listed for a check -
          autocad_checklist's overlap check reports without changing.

    Error Handling:
        - Over 20,000 curves (or 200,000 objects in the space) is refused:
          give layers or handles, or type OVERKILL in AutoCAD.
        - A locked layer among the objects to change is named, and nothing
          is changed.
        - confirm=true without the listing's plan_id, or after the drawing
          changed, does nothing and says to list again.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        items, scanned = _curves_in(doc, space, layers, handles)
        found = overkill_geometry.plan(items, tolerance, ignore_layer, join_end_to_end, tidy_polylines)
        widths: dict[str, float] = {}
        if found["rebuild"]:
            # Widths are read only for the polylines to rebuild: one whose width
            # changes along it is left, as the everyday 2D edits leave it.
            by_handle = {str(i["handle"]): i for i in items}
            for row in found["rebuild"]:
                try:
                    widths[row["handle"]] = _width(doc.HandleToObject(row["handle"]))
                except AutocadError:
                    by_handle[row["handle"]]["width_varies"] = True
            if len(widths) < len(found["rebuild"]):
                found = overkill_geometry.plan(items, tolerance, ignore_layer, join_end_to_end, tidy_polylines)
        fingerprint = _fingerprint(found)
        result: dict[str, Any] = {
            "confirmed": False,
            "plan_id": fingerprint,
            "objects_read": scanned,
            "looked_at": found["looked_at"],
            "erase_count": len(found["erase"]),
            "stretch_count": len(found["change"]),
            "erase": _short(found["erase"]),
            "change": _short(found["change"]),
            "left": _short(found["left"], 100),
            "left_count": len(found["left"]),
            "skipped_count": len(found["skipped"]),
            "skipped": _short(found["skipped"], 20),
        }
        if tidy_polylines:
            result["rebuild_count"] = len(found["rebuild"])
            result["rebuild"] = _short(found["rebuild"])
        if max(len(found["erase"]), len(found["change"]), len(found["rebuild"])) > MOST_LISTED:
            result["listed"] = f"The first {MOST_LISTED} of each are listed; the counts are whole."
        if not found["erase"] and not found["change"] and not found["rebuild"]:
            result["note"] = "Nothing doubled or overlapping was found. Nothing was changed."
            return result
        if not confirm:
            result["next_step"] = (
                "Nothing was changed. Show the modeller this list (autocad_show can point at the "
                f"handles), and call again with the same options, confirm=true and plan_id='{fingerprint}' "
                "once they agree."
            )
            return result
        if plan_id != fingerprint:
            raise AutocadError(
                "Nothing was changed: "
                + ("confirm=true needs the plan_id the listing call gave, so only what was listed is done. "
                   if not plan_id else
                   "the drawing (or the options) changed since that list, so it is not what the modeller saw. ")
                + "Call again without confirm to list it, show it, then confirm with the new plan_id."
            )
        acting_on = {r["handle"] for r in found["erase"] + found["change"] + found["rebuild"]}
        touched = {str(i["layer"]) for i in items if i["handle"] in acting_on}
        locked = _locked(doc, touched)
        if locked:
            raise AutocadError(
                f"Layer(s) {', '.join(locked)} are locked, and objects to erase or stretch are on them. "
                "Unlock them first (autocad_set_layer_state). Nothing was changed."
            )
        with undo_mark(doc):
            for row in found["change"]:
                entity = doc.HandleToObject(row["handle"])
                if row["type"] == "line":
                    entity.StartPoint = point(row["start"], "start")
                    entity.EndPoint = point(row["end"], "end")
                else:
                    entity.StartAngle = float(row["start_angle"])
                    entity.EndAngle = float(row["end_angle"])
            for row in found["rebuild"]:
                # The same polyline (same handle), its vertices and bulges set again.
                path = {"vertices": row["vertices"], "bulges": row["bulges"], "closed": row["closed"]}
                _write_polyline(doc.HandleToObject(row["handle"]), path, widths.get(row["handle"], 0.0))
            for row in found["erase"]:
                doc.HandleToObject(row["handle"]).Delete()
        result["confirmed"] = True
        rebuilt = f", rebuilt {len(found['rebuild'])} polyline(s)" if found["rebuild"] else ""
        result["note"] = (
            f"Erased {len(found['erase'])} and stretched {len(found['change'])}{rebuilt} in one undo step. "
            "AutoCAD asks the modeller whether to keep the erased ones erased; if they say no, "
            "the erased objects come back and the stretched lines (and rebuilt polylines) stay as they "
            "now are (nothing is lost)."
        )
        return result

    return dumps(await run(work))


# ---- Boundary (#118) ---------------------------------------------------------------

BOUNDARY_MOST_OBJECTS = 5000
BOUNDARY_LIMIT_OBJECTS = 50_000
BOUNDARY_TIMEOUT = 60.0
BOUNDARY_LONGEST = 300.0


def boundary_request(
    seed: list[float],
    window: list[list[float]] | None,
    islands: bool,
    make: str,
    most_objects: int,
    timeout: float,
) -> dict[str, Any]:
    """The plug-in's trace_boundary arguments, checked before AutoCAD is asked.

    In the axes the point and window are given in; the tool then turns them
    into world points, the window into its four corners.

    Refused here: a point that is not [x, y], a window that is not two
    corners with a size, a point outside its window, an object limit or a
    timeout out of range.
    """
    if len(seed) < 2:
        raise AutocadError("point must be [x, y] (or [x, y, z]) inside the outline.")
    x, y = float(seed[0]), float(seed[1])
    z = float(seed[2]) if len(seed) > 2 else 0.0
    if not all(math.isfinite(v) for v in (x, y, z)):
        raise AutocadError("point must be ordinary numbers.")
    if make not in ("polyline", "region"):
        raise AutocadError("make must be 'polyline' or 'region'.")
    if not 1 <= int(most_objects) <= BOUNDARY_LIMIT_OBJECTS:
        raise AutocadError(f"most_objects must be 1 to {BOUNDARY_LIMIT_OBJECTS}.")
    if not 1 <= float(timeout) <= BOUNDARY_LONGEST:
        raise AutocadError(f"timeout must be 1 to {BOUNDARY_LONGEST:.0f} seconds.")
    args: dict[str, Any] = {
        "point": [x, y, z],
        "islands": bool(islands),
        "make": make,
        "most_objects": int(most_objects),
    }
    if window is not None:
        if len(window) != 2 or any(len(c) < 2 for c in window):
            raise AutocadError("window must be two opposite corners, [[x1, y1], [x2, y2]].")
        (x1, x2), (y1, y2) = sorted((float(window[0][0]), float(window[1][0]))), sorted((float(window[0][1]), float(window[1][1])))
        if x2 - x1 <= 0 or y2 - y1 <= 0:
            raise AutocadError("The window has no width or no height: give two opposite corners round the room.")
        if not (x1 < x < x2 and y1 < y < y2):
            raise AutocadError(
                f"The point ({x:g}, {y:g}) is outside the window. Give a window round the room the point is in."
            )
        args["window"] = [[x1, y1], [x2, y2]]
    return args


@mcp.tool(name="autocad_trace_boundary", **tool_meta("Boundary: Closed Outline Round A Point"))
@tool_errors
async def autocad_trace_boundary(
    point_inside: Annotated[list[float], Field(description="A point inside the room or zone, [x, y] (or [x, y, z]). Like picking inside it at BOUNDARY's prompt.")],
    window: Annotated[
        list[list[float]] | None,
        Field(default=None, description="Two opposite corners round the room, [[x1, y1], [x2, y2]]: AutoCAD zooms there, traces only what is in view, then zooms back. Strongly advised on a big plan. Omit to trace what is on screen now."),
    ] = None,
    islands: Annotated[bool, Field(default=True, description="Also trace the outlines inside it (a column, a shaft) as islands, as BOUNDARY's island detection.")] = True,
    make: Annotated[Literal["polyline", "region"], Field(default="polyline", description="'polyline': closed polylines, the outline and one per island. 'region': one region with the islands cut out.")] = "polyline",
    most_objects: Annotated[int, Field(default=BOUNDARY_MOST_OBJECTS, ge=1, le=BOUNDARY_LIMIT_OBJECTS, description="Refuse, before tracing, when more objects than this are in the window: a trace over a whole big plan can hang AutoCAD.")] = BOUNDARY_MOST_OBJECTS,
    timeout: Annotated[float, Field(default=BOUNDARY_TIMEOUT, ge=1, le=BOUNDARY_LONGEST, description="Seconds Heron waits for the trace before it stops waiting and says so.")] = BOUNDARY_TIMEOUT,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Make a closed polyline (or region) from what is drawn round a point - BOUNDARY / BPOLY.

    For a room or zone outline to measure its area, hatch it or label it.
    Done by the Heron plug-in with AutoCAD's own boundary tracer
    (Editor.TraceBoundary). It never types -BOUNDARY or BPOLY: on a big plan
    those hung AutoCAD for over 100 seconds. The trace is kept small: with a
    window AutoCAD zooms to it first and the objects in it are counted, and
    over most_objects nothing is traced. Heron waits at most timeout seconds.

    One undo step. Returns the outline's handle and area.

    Args:
        point_inside (list[float]): a point inside the outline.
        window (Optional[list[list[float]]]): two corners round the room.
        islands (bool): trace islands too.
        make (str): 'polyline' or 'region'.
        most_objects (int): refuse above this many objects in view.
        timeout (float): seconds to wait.
        layer (Optional[str]): layer for the outline, created if missing.
        color (Optional[str|int]): its colour.
        coords (str): 'world' or 'ucs' for the point and window.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": str,
             "area": float, "net_area": float, "islands": [{"handle", "area"}],
             "objects_in_view": int, "window": bool}

    Examples:
        - Use when: "make a boundary round the plant room so I can get its
          area" — point inside, window round the room.
        - Use when: "draw a closed outline of this office for the hatch".
        - Use when: "BPOLY round the point 12500,8000".
        - Don't use when: you have the corners - autocad_draw_polyline or
          autocad_draw_rectangle draw it straight.
        - Don't use when: you only want the area of a closed polyline that
          is already there - autocad_polyline_info gives it.

    Error Handling:
        - A point outside its window, or a window with no size, is refused
          before AutoCAD is asked.
        - More objects in view than most_objects: nothing is traced; give a
          smaller window or freeze layers.
        - No closed outline round the point: nothing is made, and it says so.
        - No answer within timeout: Heron stops waiting; AutoCAD may still
          finish the trace, so look before trying again.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        # Checked in the axes the point and window are given in; then sent as world points,
        # the window as its four corners (square to the UCS, so maybe turned in the world).
        args = boundary_request(list(point_inside), window, islands, make, most_objects, timeout)
        args["point"] = world_coords(args["point"], ucs)
        if "window" in args:
            (x1, y1), (x2, y2) = args["window"]
            args["window"] = [world_coords(c, ucs)[:2] for c in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
        args["layer"] = layer
        args["color"] = to_aci(color)
        try:
            report = in_plugin("trace_boundary", args, "Tracing a boundary", timeout=float(timeout) + 5.0)
        except AutocadError as exc:
            if str(exc).startswith("Outcome unknown"):
                raise AutocadError(
                    f"Outcome unknown: the boundary trace took longer than {timeout:.0f} s, so Heron "
                    "stopped waiting. AutoCAD may still be tracing and may still make the outline: "
                    "look at the drawing before trying again (one Ctrl+Z takes it away). Next time "
                    "give a smaller window, or freeze the layers that do not bound the room."
                ) from exc
            raise
        handle = str(report.get("handle", ""))
        if not handle:
            raise AutocadError("Outcome unknown: Heron in AutoCAD gave no handle back. Look at the drawing before trying again.")
        result = {"created": True, **report}
        entity = _try(lambda: doc.HandleToObject(handle))
        result["verified"] = entity is not None
        if entity is None:
            result["warning"] = f"{handle} could not be read back straight away. Look at the drawing; do not make it again."
        return result

    return dumps(await run(work))


# ---- eTransmit (#114) --------------------------------------------------------------


def _drawing_file(doc: Any) -> str:
    full = str(_try(lambda: doc.FullName, "") or "")
    if not full or not os.path.isfile(full):
        raise AutocadError(
            "This drawing has never been saved, so there is no file to pack. Save it first "
            "(autocad_save_drawing), then pack it."
        )
    if not bool(_try(lambda: doc.Saved, False)):
        raise AutocadError(
            "This drawing has changes that are not saved. eTransmit packs the drawing as it is on "
            "disk: save it first (autocad_save_drawing), then pack it."
        )
    return full


def _windows_font(path: str) -> bool:
    """True for a font in Windows' own Fonts folder: every PC has those, and they are not Heron's to hand out."""
    fonts = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    return os.path.normcase(os.path.dirname(os.path.abspath(path))) == os.path.normcase(os.path.abspath(fonts))


def gather(doc: Any, full: str, deps: dict[str, Any], plot_style_folders: list[str]) -> tuple[list[transmittal.Need], list[str], list[str]]:
    """Every file the drawing needs, found or not; the Windows fonts it uses; the xrefs not looked inside.

    Xrefs come nested too, then images, underlays, fonts and plot styles.
    An xref that is not loaded is packed, but what it needs in turn
    (its own xrefs, images and fonts) could not be read, so it is named.
    """
    folder = os.path.dirname(full)
    needs = [transmittal.Need("drawing", os.path.basename(full), full)]
    windows_fonts: list[str] = []
    unread: list[str] = []
    loaded = {str(x.get("name", "")).lower(): str(x.get("file", "")) for x in deps.get("xrefs", [])}
    for node in _walk(_xref_nodes(doc.Blocks, folder, 1, {full.lower()})):
        found = node["found_path"]
        if not found:
            file = loaded.get(node["name"].lower(), "")
            found = file if file and os.path.isfile(file) else ""
        needs.append(transmittal.Need("xref", node["saved_path"] or node["name"], found, node["name"]))
        if node["status"] == "unloaded":
            unread.append(node["name"])
    for kind, key in (("image", "images"), ("underlay", "underlays"), ("font", "fonts")):
        for row in deps.get(key, []):
            name = str(row.get("name", ""))
            found = str(row.get("found", "") or "")
            if not found or not os.path.isfile(found):
                found = transmittal.find_file(name, [folder])
            if kind == "font" and found and _windows_font(found):
                windows_fonts.append(os.path.basename(found))
                continue
            needs.append(transmittal.Need(kind, name, found, str(row.get("used_by", ""))))
    for row in deps.get("plot_styles", []):
        name = str(row.get("name", ""))
        if name:
            needs.append(transmittal.Need("plot style", name, transmittal.find_file(name, plot_style_folders), str(row.get("used_by", ""))))
    return needs, windows_fonts, sorted(set(unread), key=str.lower)


NO_REWRITE = (
    "The Heron plug-in in AutoCAD cannot rewrite the paths saved in the packed drawings (it is "
    "older than this server): the pack relies on AutoCAD finding each xref, image and underlay by "
    "its bare name beside the drawing, as before. Rebuild and reinstall the plug-in to have them rewritten."
)


def retarget_copies(found: dict[str, Any], staging: Path) -> tuple[dict[str, str], dict[str, Any]]:
    """Each packed drawing copied into ``staging`` with its saved paths set to the files beside it (#160, D-149).

    The plug-in opens each copy as a side database, never the drawing on
    screen. Returns the copies to pack in place of the originals, by name in
    the pack, and what was done. A plug-in without the operation leaves
    every original as it is (the pack as before, D-114's fallback); a copy
    the plug-in could not do, or whose answer never came, is packed from the
    original, as it was. The modeller's stop or a padlock is raised: nothing
    has been written yet.
    """
    names, clashing = transmittal.pack_names(found)
    sources: dict[str, str] = {}
    drawings: list[dict[str, Any]] = []
    not_rewritten: list[dict[str, str]] = []
    for row in transmittal.drawings_to_retarget(found):
        copy = staging / row["to"]
        shutil.copy2(row["from"], copy)
        try:
            answer = in_plugin(
                "retarget_pack_paths",
                {"file": str(copy), "names": names, "clashing": clashing},
                "Rewriting the paths in the packed drawings",
                changes=False,
            )
        except BridgeRefused as exc:
            if OLD_PLUGIN in str(exc) or "does not have the operation" in str(exc):
                return {}, {"rewritten": False, "why": NO_REWRITE}
            raise
        except AutocadError as exc:
            # The copy is not used: the original goes in, with its paths as they were.
            not_rewritten.append({"file": row["to"], "why": str(exc)})
            continue
        sources[row["to"]] = str(copy)
        drawings.append({"file": row["to"], "changed": list(answer.get("changed") or []),
                         "kept": list(answer.get("kept") or [])})
    paths: dict[str, Any] = {"rewritten": bool(drawings), "drawings": drawings}
    if not_rewritten:
        paths["not_rewritten"] = not_rewritten
    return sources, paths


@mcp.tool(name="autocad_etransmit", **tool_meta("eTransmit: Pack A Drawing With Its Files"))
@tool_errors
async def autocad_etransmit(
    as_zip: Annotated[bool, Field(default=True, description="true (the default): one .zip. false: a folder.")] = True,
    folder: Annotated[str | None, Field(default=None, description="Where to put the pack. Omit for the drawing's own folder.")] = None,
    name: Annotated[str | None, Field(default=None, description="Name of the pack, without .zip. Omit for '<drawing> - Transmittal <date>'.")] = None,
    list_only: Annotated[bool, Field(default=False, description="true: only list what would be packed and what is missing; write nothing.")] = False,
) -> str:
    """Pack this drawing with everything it needs - AutoCAD's eTransmit.

    For issuing a drawing to a consultant: the saved drawing, its xrefs
    (nested ones too), raster images, PDF / DWF / DGN underlays, the font
    files its text styles use and the plot style tables its layouts use, all
    in one folder (or one .zip) beside the drawing, with a 'transmittal
    report.txt' listing what was packed and what was missing. Nothing is
    ever written over: an earlier pack of the same name gets ' (2)'.

    The drawing is packed as last saved, so an unsaved drawing is refused.
    Windows' own TrueType fonts are listed, not packed.

    In the packed copies (the drawing and each xref drawing) the xref,
    image and underlay paths are set to the bare file name of the file
    beside them, as eTransmit does, by the plug-in opening each copy on its
    own (never the drawing on screen): the original drawing is untouched.
    An older plug-in leaves the paths as saved and says so ('paths').

    Writes files: needs the Publish padlock. Changes nothing in the drawing.

    Args:
        as_zip (bool): a .zip (true) or a folder (false).
        folder (Optional[str]): where to put it; the drawing's folder if omitted.
        name (Optional[str]): the pack's name.
        list_only (bool): list only, write nothing.

    Returns:
        str: JSON: {"pack": str, "packed": [{"kind", "name", "from", "to",
             "used_by"}], "missing": [{"kind", "name", "used_by"}],
             "clashes": [...], "system_fonts": [str], "written": [str],
             "paths": {"rewritten": bool, "drawings": [{"file", "changed":
             [{"kind", "name", "was", "now"}], "kept": [{"kind", "name",
             "path", "why"}]}], "not_rewritten", "why"}}

    Examples:
        - Use when: "eTransmit this drawing to send to the consultant".
        - Use when: "zip the drawing with its xrefs and fonts".
        - Use when: "what files does this drawing need? Is anything
          missing?" — list_only=true.
        - Don't use when: you want a PDF of the sheets - autocad_publish_pdf.
        - Don't use when: you only want the xref tree and broken paths -
          autocad_xref_tree.

    Error Handling:
        - An unsaved drawing, or one with unsaved changes, is refused: save
          it first.
        - A folder that does not exist is refused before anything is written.
        - Files not found are listed under 'missing', never guessed.
    """
    target_folder = None
    if folder:
        target_folder = Path(os.path.abspath(os.path.expandvars(os.path.expanduser(folder.strip().strip('"')))))
        if not target_folder.is_dir():
            raise AutocadError(f"The folder '{target_folder}' does not exist. Give an existing folder.")
    if name is not None and (not name.strip() or any(c in name for c in '<>:"/\\|?*')):
        raise AutocadError("name must be a plain file name, without <>:\"/\\|?*.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        full = _drawing_file(doc)
        deps = in_plugin("list_dependencies", {}, "eTransmit", changes=False)
        plot_folder = str(_try(lambda: doc.Application.Preferences.Files.PrinterStyleSheetPath, "") or "")
        needs, windows_fonts, unread = gather(doc, full, deps, [f for f in plot_folder.split(";") if f.strip()])
        found = transmittal.plan(needs)
        result: dict[str, Any] = {
            "drawing": full,
            "packed": found["packed"],
            "missing": found["missing"],
            "clashes": found["clashes"],
            "system_fonts": sorted({str(f) for f in [*deps.get("system_fonts", []), *windows_fonts]}, key=str.lower),
        }
        if unread:
            result["not_looked_inside"] = unread
            result["not_looked_inside_note"] = (
                "These xrefs are not loaded, so the xrefs, images and fonts inside them were not looked "
                "for. Reload them (autocad_manage_xref action='reload') and pack again to include those."
            )
        stem = name.strip() if name else f"{Path(full).stem} - Transmittal {_dt.date.today().isoformat()}"
        target = transmittal.free_target(target_folder or Path(full).parent, stem, as_zip)
        result["pack"] = str(target)
        if list_only:
            result["written"] = []
            result["paths_to_rewrite_in"] = [row["to"] for row in transmittal.drawings_to_retarget(found)]
            result["note"] = "Nothing was written (list_only)."
            return result
        staging = Path(tempfile.mkdtemp(prefix="heron-etransmit-"))
        try:
            try:
                sources, paths = retarget_copies(found, staging)
            except OSError as exc:
                raise AutocadError(f"Could not copy the drawings to pack ({com_message(exc)}). Nothing was written.") from exc
            result["paths"] = paths
            report = transmittal.report_text(full, _dt.datetime.now().strftime("%Y-%m-%d %H:%M"), found, paths)
            try:
                result["written"] = transmittal.write(found, target, as_zip, report, sources)
            except OSError as exc:
                raise AutocadError(f"Could not write the pack at {target} ({com_message(exc)}).") from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        if found["missing"]:
            result["warning"] = (
                f"{len(found['missing'])} file(s) the drawing names were not found and are not in the "
                "pack; they are listed under 'missing' and in the report."
            )
        return result

    return dumps(await run(work))
