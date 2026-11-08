"""Materials and rendering: how a model looks, as opposed to what shape it is.

What AutoCAD's automation interface actually allows here is narrower than the
Materials Browser suggests, and the difference matters enough to state up
front:

* **Every entity has a ``Material`` property**, a string naming a material in
  the drawing. Setting it is how a material gets applied, and that works.
* **A material has to be in the drawing.** There is no automation route into
  Autodesk's material library. A material can be *made* from its settings
  (colour, texture image, gloss, transparency, glow) with
  ``autocad_create_material``, which the Heron plug-in does through AutoCAD's
  .NET API (D-42); COM cannot set those.
* **A material carries no density.** It is appearance only. MASSPROP and this
  server's ``autocad_solid_properties`` both work as if density were 1, so a
  weight is volume times a density *you* supply. Assigning "Steel" to a solid
  does not make it weigh anything.
* **Rendering has no automation call at all.** The only route is the ``-render``
  command, so ``autocad_render`` drives that — which is why it needs the Admin
  padlock, and why it reports what it sent rather than pretending to more
  certainty than it has.

The honest summary: materials can be made, listed and applied; a render can be
asked for; nothing comes from Autodesk's library.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad.entities import resolve_handles, short_type
from ..acad.render import (
    IMAGE_EXTENSIONS,
    KELVIN_MAX,
    KELVIN_MIN,
    check_rgb,
    kelvin_to_rgb,
)
from ..acad.selection import select_filtered
from ..acad.tables import validate_name
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ._shared import in_plugin

# AutoCAD's built-in render presets, in the order its own prompt lists them.
RENDER_PRESETS = ("Low", "Medium", "High", "Coffee-Break", "Lunch", "Overnight")

# Common image sizes for a render, so a sensible one can be named.
RENDER_SIZES: dict[str, tuple[int, int]] = {
    "small": (800, 600),
    "medium": (1280, 960),
    "large": (1920, 1440),
    "print": (3300, 2550),
}


def _try(getter, default=None):
    try:
        return getter()
    except BaseException:  # noqa: BLE001 - absent properties are expected here
        return default


def material_names(doc: Any) -> list[str]:
    """Every material in the drawing, by name.

    The Materials collection is iterated by index rather than with ``for``,
    because the COM collection does not always present a Python iterator.
    """
    found: list[str] = []
    table = _try(lambda: doc.Materials)
    if table is None:
        return found
    count = _try(lambda: int(table.Count), 0) or 0
    for i in range(count):
        item = _try(lambda i=i: table.Item(i))
        if item is None:
            continue
        name = _try(lambda it=item: str(it.Name))
        if name:
            found.append(name)
    return found


def match_name(wanted: str, available: list[str]) -> str | None:
    """The material in the drawing that the caller meant, ignoring case."""
    lowered = {name.lower(): name for name in available}
    return lowered.get(wanted.strip().lower())


@mcp.tool(name="autocad_list_materials", **tool_meta("List Materials"))
@tool_errors
async def autocad_list_materials() -> str:
    """List the materials in this drawing, and which objects are using them.

    Worth running before you try to apply one: only a material already in the
    drawing can be applied, and this is the list of those. If what you want is
    not here, make it with autocad_create_material, or bring it in through
    AutoCAD's own Materials Browser — there is no automation route into
    Autodesk's library.

    Reads only.

    Returns:
        str: JSON: {"count": int, "materials": [{"name", "description",
             "in_use": int}], "note": str}

    Examples:
        - Use when: "what materials does this drawing have" before applying one.
        - Use when: a material name was refused and you need the real spelling.
        - Don't use when: you want the weight of something — a material carries
          no density. Use autocad_solid_properties for the volume and multiply
          by a density you state.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        names = material_names(doc)
        used: dict[str, int] = {}
        space = _try(lambda: doc.ModelSpace)
        if space is not None:
            count = _try(lambda: int(space.Count), 0) or 0
            for i in range(count):
                item = _try(lambda i=i: space.Item(i))
                name = _try(lambda it=item: str(it.Material)) if item is not None else None
                if name:
                    used[name] = used.get(name, 0) + 1

        table = _try(lambda: doc.Materials)
        rows = []
        for name in names:
            entry = _try(lambda n=name: table.Item(n)) if table is not None else None
            rows.append({
                "name": name,
                "description": _try(lambda e=entry: str(e.Description)) if entry else None,
                "in_use": used.get(name, 0),
            })
        return {
            "count": len(rows),
            "materials": rows,
            "note": (
                "Only a material listed here can be applied. Make others with "
                "autocad_create_material, or bring them in through AutoCAD's Materials "
                "Browser: automation cannot reach the library. A material is appearance "
                "only and carries no density."
            ),
        }

    return dumps(await run(work))


@mcp.tool(name="autocad_apply_material", **tool_meta("Apply A Material"))
@tool_errors
async def autocad_apply_material(
    material: Annotated[
        str,
        Field(
            min_length=1,
            description=(
                "The material's name, exactly as it is in the drawing — "
                "autocad_list_materials gives the spellings. Pass 'ByLayer' to hand the "
                "objects back to their layer's material."
            ),
        ),
    ],
    handles: Annotated[list[str] | None, Field(default=None, description="The objects to apply it to. Give this or layer_filter.")] = None,
    layer_filter: Annotated[str | None, Field(default=None, description="Apply it to everything on this layer instead, e.g. 'S-BEAM'. Wildcards allowed, as in 'A-WALL*'.")] = None,
    solids_only: Annotated[bool, Field(default=True, description="Only apply it to 3D solids. On by default: a material on a line does nothing but clutter the drawing.")] = True,
) -> str:
    """Apply a material to objects, for rendering and shaded views.

    Materials change how a model *looks* — in a shaded or realistic visual
    style, and in a render. They do not change its geometry and they do not
    give it a weight.

    The material must already be in the drawing (autocad_create_material makes
    one). If it is not, this says so and lists what is, rather than silently
    doing nothing.

    One undo step.

    Args:
        material (str): the material's name, or 'ByLayer'.
        handles (Optional[list[str]]): the objects. Give this or layer_filter.
        layer_filter (Optional[str]): apply to everything on this layer.
        solids_only (bool): skip anything that is not a 3D solid. Default true.

    Returns:
        str: JSON: {"material", "applied": int, "skipped": int,
             "handles": [str], "failed": [{"handle", "reason"}]}

    Examples:
        - Use when: "make those beams look like steel" — material='Steel',
          layer_filter='S-BEAM'.
        - Use when: "put the concrete material on the slab" before a render or
          a shaded view.
        - Don't use when: the material is not in the drawing yet — make it
          with autocad_create_material first; autocad_list_materials shows
          what is available.
    """
    if bool(handles) == bool(layer_filter):
        raise AutocadError("Give either 'handles' or 'layer_filter' — one of the two.")
    wanted = material.strip()

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        available = material_names(doc)
        by_layer = wanted.lower() == "bylayer"
        real = "ByLayer" if by_layer else match_name(wanted, available)
        if real is None:
            raise AutocadError(
                f"There is no material called '{wanted}' in this drawing. "
                + (f"It has: {', '.join(sorted(available))}. " if available else "It has none. ")
                + "Make it with autocad_create_material, or bring it in through AutoCAD's "
                "Materials Browser — automation cannot reach Autodesk's library."
            )

        if handles:
            targets = list(resolve_handles(doc, handles))
        else:
            targets = list(select_filtered(doc, layer=layer_filter))

        applied: list[str] = []
        failed: list[dict[str, Any]] = []
        skipped = 0
        with undo_mark(doc):
            for entity in targets:
                handle = _try(lambda e=entity: str(e.Handle), "?")
                if solids_only and short_type(entity) != "3dsolid":
                    skipped += 1
                    continue
                try:
                    entity.Material = real
                except BaseException as exc:  # noqa: BLE001
                    failed.append({"handle": handle, "reason": com_message(exc)})
                    continue
                applied.append(handle)

        payload: dict[str, Any] = {
            "material": real,
            "applied": len(applied),
            "handles": applied,
        }
        if skipped:
            payload["skipped"] = skipped
            payload["skipped_note"] = (
                "Not 3D solids, so a material would not show. Pass solids_only=false to "
                "apply it anyway."
            )
        if failed:
            payload["failed"] = failed
        if not applied:
            raise AutocadError(
                f"'{real}' was applied to nothing. "
                + (f"{skipped} object(s) were not 3D solids. " if skipped else "")
                + "; ".join(f"{f['handle']}: {f['reason']}" for f in failed)
            )
        payload["note"] = (
            "Set a shaded or realistic visual style to see it: "
            "autocad_set_3d_view(visual_style='realistic')."
        )
        return payload

    return dumps(await run(work))


# Names AutoCAD keeps for itself in every drawing's material list.
RESERVED_MATERIALS = ("global", "bylayer", "byblock")


def image_path(value: str | None, name: str) -> str | None:
    """An image file on this PC, as a full path, or a refusal that says what is wrong."""
    if value is None or not value.strip():
        return None
    path = os.path.normpath(os.path.abspath(os.path.expanduser(value.strip())))
    if not path.lower().endswith(IMAGE_EXTENSIONS):
        raise AutocadError(
            f"'{path}' is not an image AutoCAD takes for {name}: use "
            + ", ".join(IMAGE_EXTENSIONS) + "."
        )
    if not os.path.isfile(path):
        raise AutocadError(f"There is no file at '{path}' for {name}.")
    return path


TEXTURE_SIZE_MAX = 1_000_000.0  # the plug-in's TextureScale.Largest
TEXTURE_SIZE_WARNING = (
    "Texture size not set: the image repeats every 1 unit (1 mm in a metric drawing), so it "
    "renders as a flat colour. Make it again with replace=true and texture_size, the real width "
    "of one image tile, e.g. 1000 for 1 m."
)


def check_texture_size(
    width: float | None, height: float | None, has_image: bool
) -> tuple[float, float] | None:
    """(width, height) of one image tile in drawing units, or None when not given."""
    if width is None:
        if height is not None:
            raise AutocadError("texture_height needs texture_size (the tile's width) too.")
        return None
    if not has_image:
        raise AutocadError("texture_size sizes a texture or bump image: give texture or bump too.")
    sizes = (float(width), float(height if height is not None else width))
    for value in sizes:
        if not (0 < value <= TEXTURE_SIZE_MAX):
            raise AutocadError(
                f"The texture size must be above zero and at most {TEXTURE_SIZE_MAX:.0f} drawing units."
            )
    return sizes


@mcp.tool(name="autocad_create_material", **tool_meta("Create A Material"))
@tool_errors
async def autocad_create_material(
    name: Annotated[
        str,
        Field(min_length=1, description="The material's name, e.g. 'Laterite Stone', 'Teak Veneer', 'LED Strip 3000K'."),
    ],
    diffuse_rgb: Annotated[
        list[int] | None,
        Field(default=None, description="Its colour, [red, green, blue] 0-255, e.g. [196, 98, 45] for laterite. Omit to take the object's own colour, or with a texture."),
    ] = None,
    texture: Annotated[
        str | None,
        Field(default=None, description="An image laid on the surface (wood grain, stone, tiles): a full path to a .jpg, .png, .tif or .bmp on this PC."),
    ] = None,
    texture_size: Annotated[
        float | None,
        Field(
            default=None, gt=0, le=TEXTURE_SIZE_MAX,
            description=(
                "The real width of one image tile, in drawing units, e.g. 1000 for a 1 m walnut "
                "veneer photo in a mm drawing, 600 for a 600 mm floor tile. Sizes the bump image too. "
                "Omit and the image repeats every 1 unit, which renders as a flat colour."
            ),
        ),
    ] = None,
    texture_height: Annotated[
        float | None,
        Field(
            default=None, gt=0, le=TEXTURE_SIZE_MAX,
            description="With texture_size, for an image that is not square: the real height of one tile. Omit for square.",
        ),
    ] = None,
    glossiness: Annotated[
        float | None,
        Field(default=None, ge=0, le=1, description="0 matt (plaster, laterite) to 1 mirror-polished (granite, glazed tile)."),
    ] = None,
    reflectivity: Annotated[
        float | None,
        Field(default=None, ge=0, le=1, description="How much it reflects its surroundings: 0 none, 0.1 polished floor, 0.9 a mirror."),
    ] = None,
    transparency: Annotated[
        float | None,
        Field(default=None, ge=0, le=1, description="0 solid, 1 fully clear. Clear glass about 0.9, frosted about 0.5."),
    ] = None,
    refraction_index: Annotated[
        float | None,
        Field(default=None, ge=1, le=5, description="With transparency: how it bends light. Glass 1.5, water 1.33."),
    ] = None,
    luminance: Annotated[
        float | None,
        Field(default=None, ge=0, le=1_000_000, description="Makes it glow, in cd/m² (self-illumination): an LED strip about 1000-3000, a lit panel about 500."),
    ] = None,
    glow_kelvin: Annotated[
        float | None,
        Field(default=None, ge=KELVIN_MIN, le=KELVIN_MAX, description="The white it glows in: 2700-3000 warm, 4000 neutral, 6500 daylight. Sets the colour, so give this or diffuse_rgb."),
    ] = None,
    bump: Annotated[
        str | None,
        Field(default=None, description="A greyscale image for a raised or rough surface (stone joints, rough plaster): full path, as texture."),
    ] = None,
    bump_amount: Annotated[
        float,
        Field(default=0.3, ge=0, le=1, description="How strong the bump is, 0-1."),
    ] = 0.3,
    metallic: Annotated[bool, Field(default=False, description="Shade it as a metal (steel, brass, aluminium).")] = False,
    description: Annotated[str | None, Field(default=None, description="A line saying what it is, shown in AutoCAD's Materials Browser.")] = None,
    replace: Annotated[
        bool,
        Field(default=False, description="Change a material of this name that is already in the drawing; everything using it changes too."),
    ] = False,
) -> str:
    """Make a material in this drawing from its look: colour, texture, gloss, glass, glow.

    For renders and realistic views: laterite walls, teak doors, granite
    floors, glass, and glowing LED strips. Once made, autocad_apply_material
    puts it on objects straight away.

    Only the settings given are written; everything else keeps AutoCAD's
    default. Give a texture its real size with texture_size (the width of one
    image tile in drawing units; texture_height too for a non-square image):
    without it AutoCAD repeats the image every 1 unit (1 mm in a metric
    drawing) and it renders as a flat colour, so the result warns. The same
    size is used for the bump image. Width runs along X; height along Y and up
    the walls (Z).

    A glow (luminance) takes the material's colour: AutoCAD's API has no
    separate glow colour, so glow_kelvin sets the colour to that white.

    One undo step. Done by Heron's plug-in in AutoCAD (COM cannot set a
    material's colour, maps or glow).

    Args:
        name (str): the material's name.
        diffuse_rgb (Optional[list[int]]): its colour.
        texture (Optional[str]): image laid on the surface.
        texture_size (Optional[float]): real width of one image tile, drawing units.
        texture_height (Optional[float]): real height of one tile, if not square.
        glossiness / reflectivity / transparency (Optional[float]): 0-1.
        refraction_index (Optional[float]): glass 1.5.
        luminance (Optional[float]): glow, cd/m².
        glow_kelvin (Optional[float]): the white it glows in.
        bump (Optional[str]), bump_amount (float): a rough surface.
        metallic (bool): shade as metal.
        description (Optional[str]): a line saying what it is.
        replace (bool): change one that is already there.

    Returns:
        str: JSON: {"created" | "replaced": true, "name": str, "handle": str,
             "set": [str], "in_drawing": bool, "next": str,
             "texture_size"?: [width, height], "warning"?: str}

    Examples:
        - Use when: "make a laterite stone material for the boundary wall" —
          diffuse_rgb=[178, 84, 52], glossiness=0.1, and a texture if there is
          a photo of the stone.
        - Use when: "make the window glass" — transparency=0.9,
          refraction_index=1.5, reflectivity=0.1.
        - Use when: "the cove LED strip must glow warm white in the night
          render" — luminance=2000, glow_kelvin=3000.
        - Use when: "make a teak wood material from this image" —
          texture='D:/Textures/teak.jpg', texture_size=1000.
        - Use when: "walnut veneer, 1 m grain" — texture=<the walnut .jpg>,
          texture_size=1000 in a mm drawing, so the grain shows instead of a
          flat brown.
        - Use when: "white marble floor, 2 m slab" or "600 x 300 wall tile" —
          texture_size=2000, or texture_size=600 with texture_height=300.
        - Don't use when: the material is already in the drawing — apply it
          with autocad_apply_material (autocad_list_materials lists them).
        - Don't use when: the room must actually be lit — a glowing material
          lights little around it; add lights with autocad_add_light.

    Error Handling:
        - A name already in the drawing is refused unless replace=true.
        - An image path that is not there, or not an image, is refused.
        - texture_size without a texture or bump image, or texture_height
          without texture_size, is refused.
        - Both diffuse_rgb and glow_kelvin is refused: the glow takes the
          colour.
        - Needs the Heron plug-in 1.4.0 or newer in AutoCAD; texture_size
          needs 1.4.1 (an older one ignores it, and the result warns).
    """
    clean = validate_name(name, "material")
    if clean.lower() in RESERVED_MATERIALS:
        raise AutocadError(f"'{clean}' is AutoCAD's own material name. Choose another.")
    colour = check_rgb(diffuse_rgb, "diffuse_rgb")
    if colour is not None and glow_kelvin is not None:
        raise AutocadError(
            "Give diffuse_rgb or glow_kelvin, not both: the glow takes the material's colour, "
            "so glow_kelvin sets that colour."
        )
    if glow_kelvin is not None:
        colour = kelvin_to_rgb(glow_kelvin)
    if refraction_index is not None and not transparency:
        raise AutocadError("refraction_index bends light through a clear material: give transparency too.")
    image = image_path(texture, "texture")
    rough = image_path(bump, "bump")
    tile = check_texture_size(texture_size, texture_height, bool(image or rough))

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        args: dict[str, Any] = {
            "name": clean,
            "diffuse_rgb": colour,
            "texture": image,
            "glossiness": glossiness,
            "reflectivity": reflectivity,
            "opacity": None if transparency is None else round(1.0 - float(transparency), 9),
            "refraction_index": refraction_index,
            "luminance": luminance,
            "bump": rough,
            "bump_amount": float(bump_amount) if rough else None,
            "texture_size": tile[0] if tile else None,
            "texture_height": tile[1] if tile and texture_height is not None else None,
            "metallic": True if metallic else None,
            "description": description.strip() if description and description.strip() else None,
            "replace": bool(replace),
        }
        report = in_plugin("create_material", args, "Making a material")
        # Read it back the way autocad_apply_material will look for it.
        there = match_name(clean, material_names(doc)) is not None
        payload: dict[str, Any] = dict(report)
        payload["in_drawing"] = there
        if glow_kelvin is not None:
            payload["glow_rgb"] = colour
        warnings: list[str] = []
        if (image or rough) and tile is None:
            warnings.append(TEXTURE_SIZE_WARNING)
        elif tile is not None and "texture size" not in (report.get("set") or []):
            warnings.append(
                "Heron in AutoCAD did not set the texture size (a plug-in older than 1.4.1 ignores it), "
                "so the image repeats every 1 unit. Update the plug-in, then make it again with replace=true."
            )
        if there:
            payload["next"] = (
                f"Apply it with autocad_apply_material(material='{clean}', ...), then look at it "
                "with autocad_set_3d_view(visual_style='realistic')."
            )
        else:
            warnings.append(
                f"Heron in AutoCAD made '{clean}', but it could not be read back from the drawing's "
                "material list straight away. Check autocad_list_materials; do not make it again."
            )
        if warnings:
            payload["warning"] = " ".join(warnings)
        return payload

    return dumps(await run(work))


@mcp.tool(name="autocad_render", **tool_meta("Render The Model"))
@tool_errors
async def autocad_render(
    output_path: Annotated[
        str,
        Field(
            min_length=1,
            description=(
                "Where to write the image, with its extension — .png, .jpg or .tif. An "
                "absolute Windows path, e.g. 'C:/Jobs/A-101/view.png'."
            ),
        ),
    ],
    preset: Annotated[
        Literal["Low", "Medium", "High", "Coffee-Break", "Lunch", "Overnight"],
        Field(
            default="Medium",
            description=(
                "Render quality, as AutoCAD names it. Low and Medium are quick looks; "
                "Coffee-Break, Lunch and Overnight are named for how long they take, "
                "and they mean it."
            ),
        ),
    ] = "Medium",
    size: Annotated[
        Literal["small", "medium", "large", "print"],
        Field(default="medium", description="Image size: small 800x600, medium 1280x960, large 1920x1440, print 3300x2550."),
    ] = "medium",
    width: Annotated[int | None, Field(default=None, ge=16, le=10000, description="An exact width in pixels instead of 'size'.")] = None,
    height: Annotated[int | None, Field(default=None, ge=16, le=10000, description="An exact height in pixels instead of 'size'.")] = None,
) -> str:
    """Render the current view to an image file.

    **Read this before using it.** Rendering has no automation call in AutoCAD;
    the only route is the ``-render`` command, so this sends that command and
    its answers. Three consequences, all of them real:

    * It needs the **Admin** padlock, because it drives the command line.
    * The prompt wording differs between releases, so the command can stall
      part-way waiting for an answer this tool did not anticipate. If the image
      does not appear, press Esc in AutoCAD and render by hand.
    * Rendering from a script has been reported to drop objects that render
      correctly when done by hand. Check the image before you send it to anyone.

    What is reliable: set the view with ``autocad_set_3d_view`` and apply
    materials with ``autocad_apply_material`` first — those do work — and for a
    picture to put on a drawing, ``autocad_preview`` or ``autocad_export`` is
    the dependable route.

    Args:
        output_path (str): where to write the image, with its extension.
        preset (str): Low, Medium, High, Coffee-Break, Lunch or Overnight.
        size (str): small, medium, large or print.
        width / height (Optional[int]): exact pixels instead of 'size'.

    Returns:
        str: JSON: {"sent": str, "output_path", "preset", "width", "height",
             "exists": bool, "size_bytes": int | null, "note": str}

    Examples:
        - Use when: "render this view for the client" — after setting the view
          and applying materials.
        - Don't use when: you want to see what you drew — autocad_preview is
          instant, needs no padlock and always works.
        - Don't use when: the picture goes on a drawing sheet — that is
          autocad_export to PDF.
    """
    if (width is None) != (height is None):
        raise AutocadError("Give both width and height, or neither and use 'size'.")
    px = (int(width), int(height)) if width is not None else RENDER_SIZES[size]
    target = output_path.strip().replace("/", "\\")
    if "." not in target.rsplit("\\", 1)[-1]:
        raise AutocadError(
            f"'{output_path}' has no file extension. Render output needs one: .png, .jpg or .tif."
        )

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        # -render asks, in order: preset, destination, width, height, file name.
        line = f'-render\n{preset}\nFile\n{px[0]}\n{px[1]}\n{target}\n'
        try:
            doc.SendCommand(line)
        except BaseException as exc:  # noqa: BLE001
            raise AutocadError(
                f"AutoCAD would not take the render command ({com_message(exc)}). "
                "Render by hand instead: set the view, then RENDER."
            ) from exc

        exists = os.path.isfile(target)
        return {
            "sent": line.replace("\n", " | ").strip(),
            "output_path": target,
            "preset": preset,
            "width": px[0],
            "height": px[1],
            "exists": exists,
            "size_bytes": os.path.getsize(target) if exists else None,
            "note": (
                "The image was found." if exists else
                "The file is not there yet. A render at this preset can take minutes, and "
                "the command may be waiting for an answer on AutoCAD's command line — look "
                "at it. If it is stuck, press Esc and render by hand."
            ),
        }

    return dumps(await run(work))
