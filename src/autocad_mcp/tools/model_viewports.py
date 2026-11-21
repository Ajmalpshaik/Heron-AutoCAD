"""Tiled model viewports: split the Model tab into 2, 3 or 4 (VPORTS, D-111).

Model space only. Viewports on a sheet (paper space) are autocad_add_viewport.
The split changes what is on screen, not what is drawn, so it is a View job:
no Changes padlock, nothing to keep or discard.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from ..acad import tiles as tile_plan
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from ..core.variants import apoint, double_array, point_to_list

# The named configuration Heron builds the split in (VPORTS > Named Viewports).
CONFIGURATION = "Heron"
ACTIVE = "*ACTIVE"


def _tiles(doc: Any) -> list[dict[str, Any]]:
    """The Model tab's tiles: every viewport record named *Active, with its corners."""
    current = None
    try:
        active = doc.ActiveViewport
        current = (point_to_list(active.LowerLeftCorner), point_to_list(active.UpperRightCorner))
    except BaseException:  # noqa: BLE001 - which one is current is extra
        pass
    found: list[dict[str, Any]] = []
    viewports = doc.Viewports
    for index in range(int(viewports.Count)):
        viewport = viewports.Item(index)
        if str(viewport.Name).upper() != ACTIVE:
            continue
        lower = point_to_list(viewport.LowerLeftCorner)
        upper = point_to_list(viewport.UpperRightCorner)
        found.append({"lower_left": lower[:2], "upper_right": upper[:2], "current": current == (lower, upper)})
    found.sort(key=lambda t: (-t["upper_right"][1], t["lower_left"][0]))
    return found


def _copy_view(source: Any, target: Any) -> list[str]:
    """The current view (direction, target, centre, height, width) onto the new viewport; what would not copy."""
    not_copied: list[str] = []
    steps = (
        ("Direction", lambda: target.__setattr__("Direction", apoint(*point_to_list(source.Direction)[:3]))),
        ("Target", lambda: target.__setattr__("Target", apoint(*point_to_list(source.Target)[:3]))),
        ("Center", lambda: target.__setattr__("Center", double_array(point_to_list(source.Center)[:2]))),
        ("Height", lambda: target.__setattr__("Height", float(source.Height))),
        ("Width", lambda: target.__setattr__("Width", float(source.Width))),
    )
    for name, step in steps:
        try:
            step()
        except BaseException:  # noqa: BLE001 - the split still works, from AutoCAD's default view
            not_copied.append(name.lower())
    return not_copied


@mcp.tool(name="autocad_model_viewports", **tool_meta("Tiled Model Viewports", idempotent=True))
@tool_errors
async def autocad_model_viewports(
    layout: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "How to split the Model tab: 'one' (back to a single view), 'two_vertical' (two side by side), "
                "'two_horizontal' (one above the other), 'three_left' / 'three_right' / 'three_above' / "
                "'three_below' (where the big one goes), 'three_vertical' (three side by side), "
                "'three_horizontal' (three stacked), 'four' (two by two). Omit to read the split as it is."
            ),
            pattern="^(one|two_vertical|two_horizontal|three_left|three_right|three_above|three_below|three_vertical|three_horizontal|four)$",
        ),
    ] = None,
) -> str:
    """Tile the Model tab into 2, 3 or 4 viewports (VPORTS), back to one, or read the tiles as they are.

    Each new viewport starts from the view on screen now; zoom or turn each
    one by clicking in it (or autocad_zoom / autocad_set_3d_view work on the
    one that is current). The answer reads the tiles back from AutoCAD, with
    their corners as fractions of the drawing area, and says if AutoCAD split
    it another way than asked.

    Model tab only: on a layout, viewports are autocad_add_viewport. This
    changes the screen, not the drawing: it needs no Changes padlock. AutoCAD
    keeps the split as the named configuration 'Heron' (VPORTS > Named
    Viewports); Heron replaces it the next time.

    Args:
        layout (Optional[str]): the split; omit to read it.

    Returns:
        str: JSON: {"layout": str|None, "tiles": int, "arrangement": str,
             "viewports": [{"lower_left": [x, y], "upper_right": [x, y],
             "current": bool}], "view_not_copied"?: [str], "warning"?: str}

    Examples:
        - Use when: "split the screen in two so I can see the plan and the
          section side by side" — layout='two_vertical'.
        - Use when: "four viewports: top, front, side and 3D" —
          layout='four', then set each view.
        - Use when: "back to one viewport" — layout='one'.
        - Use when: "how is the model view split?" — no layout.
        - Don't use when: the viewport is on a sheet — autocad_add_viewport.
        - Don't use when: you only want to look somewhere else —
          autocad_zoom or autocad_set_3d_view.

    Error Handling:
        - On a layout it says to switch to the Model tab, and changes nothing.
        - A split AutoCAD built another way than asked is a warning with what
          it did build.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        try:
            tilemode = int(doc.GetVariable("TILEMODE"))
        except BaseException:  # noqa: BLE001 - unreadable: let the split itself say
            tilemode = 1
        if tilemode == 0:
            raise AutocadError(
                "Tiled viewports are on the Model tab, and this is a layout. Switch to the Model tab and ask "
                "again; for a viewport on this sheet use autocad_add_viewport. Nothing was changed."
            )

        result: dict[str, Any] = {"layout": layout}
        if layout is not None:
            current = doc.ActiveViewport
            try:
                doc.Viewports.DeleteConfiguration(CONFIGURATION)
            except BaseException:  # noqa: BLE001 - none left from an earlier split
                pass
            try:
                viewport = doc.Viewports.Add(CONFIGURATION)
                not_copied = _copy_view(current, viewport)
                code = tile_plan.LAYOUTS[layout]
                if code is not None:
                    viewport.Split(code)
                # A split shows only once its viewport is made active, even the current one.
                doc.ActiveViewport = viewport
            except AutocadError:
                raise
            except BaseException as exc:  # noqa: BLE001 - say what AutoCAD said
                raise AutocadError(f"AutoCAD would not split the Model tab ({com_message(exc)}).") from exc
            if not_copied:
                result["view_not_copied"] = not_copied

        found = _tiles(doc)
        arrangement = tile_plan.describe([(t["lower_left"], t["upper_right"]) for t in found])
        result.update(tiles=len(found), arrangement=arrangement, viewports=found)
        if layout is not None:
            expected = tile_plan.EXPECTED[layout]
            if arrangement != expected:
                result["warning"] = f"Asked for {expected}, but AutoCAD shows {arrangement}. Look at the screen."
            result["note"] = (
                "Click in a viewport to make it current; autocad_zoom and autocad_set_3d_view work on that one."
            )
        return result

    return dumps(await run(work))
