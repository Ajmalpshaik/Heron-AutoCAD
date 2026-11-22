"""The rest of SOLIDEDIT, done by the Heron plug-in (D-40, D-113).

Offset, taper, move and delete faces, imprint and separate have no ActiveX
call, so these ask the plug-in to do them through AutoCAD's .NET API. Each runs
in one transaction inside AutoCAD: it all lands or none of it does.

Faces are picked as the other solid edits pick them: a plain word ('top',
'front') that goes by the solid's box, or the numbers
``autocad_list_solid_faces_and_edges`` gives. The numbers hold while the solid
is unchanged: after any edit, list it again.
"""

from __future__ import annotations

import math
from typing import Annotated, Any, Literal

from pydantic import Field

from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from ._shared import (
    COORDS_OPT,
    in_plugin,
    plugin_read,
    ucs_for,
    world_coords,
    world_direction,
)
from .solid_edits import FACES_OPT, FacePick

# Which options each face edit takes; anything else given is refused, never ignored.
TAKES = {
    "offset": {"distance"},
    "taper": {"angle", "direction", "base_point"},
    "move": {"by"},
    "delete": set(),
}
NEEDS = {"offset": {"distance"}, "taper": {"angle"}, "move": {"by"}, "delete": set()}
OPERATION = {"offset": "offset_faces", "taper": "taper_faces", "move": "move_faces", "delete": "delete_faces"}
WHAT = {
    "offset": "Offsetting a solid's faces",
    "taper": "Tapering a solid's faces",
    "move": "Moving a solid's faces",
    "delete": "Deleting a solid's faces",
}


@mcp.tool(name="autocad_edit_solid_faces", **tool_meta("Offset, Taper, Move Or Delete A Solid's Faces", destructive=True))
@tool_errors
async def autocad_edit_solid_faces(
    handle: Annotated[str, Field(min_length=1, description="The 3D solid, by handle.")],
    action: Annotated[
        Literal["offset", "taper", "move", "delete"],
        Field(
            description=(
                "'offset': move faces square to themselves by distance (a hole bigger or smaller, a side thicker). "
                "'taper': lean faces by angle. 'move': shift faces by [dx, dy, dz]; the faces beside them stretch. "
                "'delete': remove faces (a fillet, a chamfer, a hole) and close the gap."
            )
        ),
    ],
    faces: Annotated[FacePick, FACES_OPT],
    distance: Annotated[
        float | None,
        Field(default=None, description="offset: how far. Positive grows the solid at those faces, negative cuts into it."),
    ] = None,
    angle: Annotated[
        float | None,
        Field(default=None, gt=-90, lt=90, description="taper: degrees. Positive is meant to lean the faces in as they rise, as SOLIDEDIT does; not proven yet, so check volume_after (smaller is in)."),
    ] = None,
    direction: Annotated[
        list[float] | None,
        Field(default=None, min_length=3, max_length=3, description="taper: the way 'rising' goes, [x, y, z]. Default up [0, 0, 1]."),
    ] = None,
    base_point: Annotated[
        list[float] | None,
        Field(
            default=None,
            min_length=2,
            max_length=3,
            description="taper: a point on the plane the faces pivot about. Default: the bottom of the picked faces, so their bottom edges stay.",
        ),
    ] = None,
    by: Annotated[
        list[float] | None,
        Field(default=None, min_length=3, max_length=3, description="move: how far, as [dx, dy, dz]."),
    ] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Offset, taper, move or delete faces of a 3D solid (SOLIDEDIT Face).

    Faces are picked by a word ('top', 'front'...) or by the numbers
    autocad_list_solid_faces_and_edges gives. Reports the volume before and
    after, so the change can be checked.

    One undo step.

    Args:
        handle (str): the solid.
        action (str): offset, taper, move or delete.
        faces (str|list[int]): a word or face numbers.
        distance (Optional[float]): offset only.
        angle (Optional[float]): taper only, degrees.
        direction (Optional[list[float]]): taper only, default up.
        base_point (Optional[list[float]]): taper only.
        by (Optional[list[float]]): move only.
        coords (str): 'world' or 'ucs' for direction, base_point and by.

    Returns:
        str: JSON: {"handle": str, "action": str, "faces": [int],
             "volume_before": float, "volume_after": float, ...}

    Examples:
        - Use when: "make the 100 hole in the plate 10 bigger all round" —
          action='offset', the hole's face number, distance=-10 (cutting into
          the solid makes the hole bigger).
        - Use when: "taper the sides of the plinth 5 degrees" — action='taper',
          faces=[side face numbers], angle=5.
        - Use when: "move the end face of the beam 200 along X" —
          action='move', faces='right', by=[200, 0, 0].
        - Use when: "take the fillet off that edge" — action='delete', the
          fillet's face number.
        - Don't use when: pulling a flat face straight out or in —
          autocad_press_pull_faces.
        - Don't use when: hollowing the solid — autocad_shell_solid.

    Error Handling:
        - An option the action does not take, or a missing one, is refused
          before AutoCAD is asked.
        - Deleting every face is refused; so is a face AutoCAD cannot close
          over (a box's side).
        - A face word that picks nothing, or a number not there, is refused
          with the range.
    """
    given = {
        name
        for name, value in (("distance", distance), ("angle", angle), ("direction", direction), ("base_point", base_point), ("by", by))
        if value is not None
    }
    stray = sorted(given - TAKES[action])
    if stray:
        raise AutocadError(f"'{action}' does not take {', '.join(stray)}. " + _takes(action))
    missing = sorted(NEEDS[action] - given)
    if missing:
        raise AutocadError(f"'{action}' needs {', '.join(missing)}. " + _takes(action))
    if action == "offset" and distance == 0:
        raise AutocadError("The distance cannot be zero: positive grows the solid at those faces, negative cuts into it.")
    if action == "taper" and angle == 0:
        raise AutocadError("A taper of 0 degrees changes nothing. Give the angle in degrees, positive to lean the faces in.")
    if action == "move" and by is not None and not any(by):
        raise AutocadError("Moving the faces by [0, 0, 0] changes nothing.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords) if given & {"direction", "base_point", "by"} else None
        args: dict[str, Any] = {"handle": handle, "faces": faces}
        if action == "offset":
            args["distance"] = float(distance or 0.0)
        elif action == "taper":
            args["angle"] = math.radians(float(angle or 0.0))
            if direction is not None:
                args["direction"] = world_direction(direction, ucs)
            if base_point is not None:
                args["base"] = world_coords(base_point, ucs)
        elif action == "move":
            args["by"] = world_direction(by or [0.0, 0.0, 0.0], ucs)
        report = in_plugin(OPERATION[action], args, WHAT[action])
        return {"action": action, **report}

    return dumps(await run(work))


def _takes(action: str) -> str:
    takes = sorted(TAKES[action])
    return f"'{action}' takes " + (", ".join(takes) if takes else "only the faces") + "."


@mcp.tool(name="autocad_imprint_solid", **tool_meta("Imprint Lines Or Shapes Onto A Solid"))
@tool_errors
async def autocad_imprint_solid(
    handle: Annotated[str, Field(min_length=1, description="The 3D solid, by handle.")],
    objects: Annotated[
        list[str],
        Field(min_length=1, description="What to imprint, by handle: lines, arcs, circles, polylines, splines, regions or solids that touch or cross the solid's faces. They are kept."),
    ],
) -> str:
    """Imprint lines or shapes onto a solid's faces (SOLIDEDIT Imprint), splitting the faces along them.

    A face split this way can then be pulled, offset or coloured on its own: a
    plinth's top split for a raised pad, a wall face split for an opening. The
    objects are kept, as SOLIDEDIT keeps them unless told otherwise. The
    result counts the faces before and after, so a miss shows.

    One undo step.

    Args:
        handle (str): the solid.
        objects (list[str]): what to imprint.

    Returns:
        str: JSON: {"handle": str, "objects": [str], "faces_before": int,
             "faces_after": int, "edges_before": int, "edges_after": int,
             "volume": float}

    Examples:
        - Use when: "imprint this rectangle on the top of the plinth so I can
          pull a pad up" — then autocad_press_pull_faces on the new face.
        - Use when: "split the wall face along this line".
        - Don't use when: you want the lines cut right through the solid —
          autocad_slice_solid or autocad_solid_boolean.

    Error Handling:
        - Anything that cannot be imprinted (text, a block) is named, with
          what it is.
        - An object that does not touch the solid changes nothing: the face
          count says so.
    """

    def work() -> dict[str, Any]:
        require_idle(get_doc())
        report = in_plugin("imprint_solid", {"handle": handle, "objects": list(objects)}, "Imprinting onto a solid")
        after, why = plugin_read("solid_topology", {"handle": handle})
        if after is None:
            report["note"] = f"Imprinted, but the faces could not be counted after ({why}). autocad_list_solid_faces_and_edges lists them."
            return report
        report["faces_after"] = len(after.get("faces", []))
        report["edges_after"] = len(after.get("edges", []))
        if report["faces_after"] == report.get("faces_before") and report["edges_after"] == report.get("edges_before"):
            report["note"] = (
                "Nothing new was imprinted: the face and edge counts did not change. The objects probably do not touch "
                "or cross the solid's faces; check them in 3D with autocad_preview."
            )
        return report

    return dumps(await run(work))


@mcp.tool(name="autocad_separate_solid", **tool_meta("Separate A Solid Into Its Pieces"))
@tool_errors
async def autocad_separate_solid(
    handle: Annotated[str, Field(min_length=1, description="The 3D solid, by handle.")],
) -> str:
    """Separate a solid made of pieces that do not touch into one solid per piece (SOLIDEDIT Separate).

    The solid keeps one piece; each other piece becomes a new solid on the same
    layer, with the same colour. Pieces that touch, even along an edge, stay
    one solid.

    One undo step.

    Args:
        handle (str): the solid.

    Returns:
        str: JSON: {"handle": str, "volume_before": float, "piece_count": int,
             "pieces": [{"handle": str, "volume": float}]}

    Examples:
        - Use when: "the union made one solid of the two pump skids, split them
          apart again".
        - Use when: "after the slice this is two lumps in one solid, separate
          them".
        - Don't use when: you want to cut a solid in two — autocad_slice_solid.

    Error Handling:
        - A solid that is one piece already is refused: there is nothing to
          separate.
    """

    def work() -> dict[str, Any]:
        require_idle(get_doc())
        return in_plugin("separate_solid", {"handle": handle}, "Separating a solid")

    return dumps(await run(work))
