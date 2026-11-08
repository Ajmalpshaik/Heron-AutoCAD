"""MCP resources and prompts.

A resource reads the drawing just as a tool does, so each one calls the
matching gated tool: it is refused the same way while AutoCAD is not
connected to Heron, and it is audited the same way.
"""

from __future__ import annotations

import re

from ..acad.findtool import Entry, search, split_bullets
from ..core.registry import dumps, mcp
from ..core.risk import RISK, Risk
from . import document, layers

_JSON = "application/json"

# What each padlock means, in the words the ribbon uses.
_PADLOCK = {
    Risk.READ: "none - reads the drawing",
    Risk.VIEW: "none - changes only what is on screen",
    Risk.CHANGE: "Changes",
    Risk.PUBLISH: "Changes + Publish",
    Risk.ADMIN: "Changes + Admin",
}

# The first line of a tool's docstring, and its "Use when" bullets.
_USE_WHEN = re.compile(r"^\s*- (Use when|Don't use when):\s*(.*)$")


def _summary(description: str) -> str:
    """The tool's one-line summary: the first line of its docstring."""
    for line in description.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _use_when(description: str) -> list[str]:
    """The Examples bullets, each joined back into one line.

    A bullet wraps over several source lines, and the SDK hands the docstring
    back dedented, so a continuation is any line indented deeper than the
    bullet that owns it. Rejoining them means the index reads as sentences
    rather than as a column of half-finished ones.
    """
    found: list[str] = []
    depth = 0
    for line in description.splitlines():
        indent = len(line) - len(line.lstrip())
        match = _USE_WHEN.match(line)
        if match:
            found.append(f"{match.group(1)}: {match.group(2)}".rstrip())
            depth = indent
            continue
        if not found:
            continue
        if not line.strip():
            continue
        if indent > depth:
            found[-1] = f"{found[-1]} {line.strip()}"
        else:
            break  # a new section started; the examples are finished
    return found


@mcp.resource("autocad://drawing/status", name="drawing_status", description="Connection, active drawing, units.", mime_type=_JSON)
async def drawing_status() -> str:
    return await document.autocad_status(launch_if_needed=False)


@mcp.resource("autocad://drawing/layers", name="drawing_layers", description="Every layer and its state.", mime_type=_JSON)
async def drawing_layers() -> str:
    return await layers.autocad_list_layers(include_entity_counts=False)


@mcp.resource("autocad://drawing/blocks", name="drawing_blocks", description="Block definitions in the drawing.", mime_type=_JSON)
async def drawing_blocks() -> str:
    return await layers.autocad_list_blocks()


@mcp.resource("autocad://drawing/styles", name="drawing_styles", description="Text styles, dimension styles, linetypes.", mime_type=_JSON)
async def drawing_styles() -> str:
    return await layers.autocad_list_styles()


@mcp.resource("autocad://tools", name="tool_index", description="Every tool, grouped by the padlock it needs, with when to use it. Needs no AutoCAD.", mime_type=_JSON)
async def tool_index() -> str:
    """The whole toolbox in one place, so the right tool is quick to find.

    101 tools is more than anyone holds in their head. This lists every one
    with its padlock, its one-line summary and its "Use when" lines, grouped
    by padlock so what a job needs is obvious before it is tried.

    It is built from the live registry, so it cannot go stale: a tool added,
    renamed or re-levelled shows up here with no second edit.

    Unlike the other resources it touches no drawing, so it is **not gated**:
    it answers before AutoCAD is open and before Heron is pressed.
    """
    groups: dict[str, list[dict[str, object]]] = {}
    for tool in await mcp.list_tools():
        level = RISK.get(tool.name, Risk.ADMIN)
        description = tool.description or ""
        groups.setdefault(level.value, []).append({
            "tool": tool.name,
            "title": tool.title or "",
            "summary": _summary(description),
            "use_when": _use_when(description),
        })
    order = [r.value for r in (Risk.READ, Risk.VIEW, Risk.CHANGE, Risk.PUBLISH, Risk.ADMIN)]
    return dumps({
        "count": sum(len(v) for v in groups.values()),
        "padlocks": {
            level: {
                "needs": _PADLOCK[Risk(level)],
                "count": len(groups.get(level, [])),
                "tools": sorted(groups.get(level, []), key=lambda row: str(row["tool"])),
            }
            for level in order
        },
        "note": (
            "A tool's padlock is a property of the tool, not of the request, so nothing you "
            "write can raise or lower it. Turn a padlock on in Settings on the Heron tab in AutoCAD."
        ),
    })


async def _entries() -> list[Entry]:
    """Every tool as the search sees it, straight from the registry."""
    rows: list[Entry] = []
    for tool in await mcp.list_tools():
        description = tool.description or ""
        use, avoid = split_bullets(_use_when(description))
        rows.append(Entry(tool.name, tool.title or "", _summary(description), use, avoid))
    return rows


@mcp.resource("autocad://tools/find/{phrase}", name="find_tool", description="The right tool for a job described in plain words. Needs no AutoCAD.", mime_type=_JSON)
async def find_tool(phrase: str) -> str:
    """Search the toolbox in the words a draftsman would use.

    Reading the whole index works, but it is a hundred entries. This answers
    "how many metres of DN50 pipe on this layer" with autocad_total_length and
    stops. Scored on the tools' own names, summaries and "Use when" lines,
    weighted so a rare word (DIMSCALE, flange) beats a common one (layer, set)
    and so a "Don't use when" mention counts against rather than for.

    Measured on 55 phrases a modeller would really say: the right tool came
    first 45 times and was in the top three all 55 times. Those phrases are
    our own, so treat it as a floor on a sample, not a promise - and when it
    puts the wrong tool first, the fix is usually that tool's own "Use when"
    line, not the scoring.

    It touches no drawing, so like autocad://tools it is **not gated**.
    """
    entries = await _entries()
    hits = search(entries, phrase, limit=5)
    by_name = {entry.tool: entry for entry in entries}
    return dumps({
        "phrase": phrase,
        "count": len(hits),
        "matches": [
            {
                "tool": hit.tool,
                "needs": _PADLOCK[RISK.get(hit.tool, Risk.ADMIN)],
                "summary": by_name[hit.tool].summary,
                "use_when": list(by_name[hit.tool].use_when),
                "matched_words": list(hit.matched),
                "score": hit.score,
            }
            for hit in hits
        ],
        "note": (
            "Best first, but read the summary before you call it: the second one is "
            "sometimes the right one. Nothing found? Read autocad://tools, the whole "
            "catalogue."
        ),
    })


@mcp.prompt(name="check_standards", description="Check the open drawing against a layer standard and show the result.")
def check_standards(rules_path: str = "") -> str:
    where = f"the rules in {rules_path}" if rules_path else "the layer standard I describe"
    return (
        "Check the drawing that is open in AutoCAD against " + where + ".\n"
        "1. Call autocad_status and tell me the drawing name and units.\n"
        "2. Call autocad_check_standards with those rules.\n"
        "3. Summarise the findings by rule, worst first, with handles I can zoom to.\n"
        "4. Do not change anything: only report."
    )


@mcp.prompt(name="draw_from_spec", description="Draw something from a written spec, then show it.")
def draw_from_spec(spec: str) -> str:
    return (
        "Draw this in the AutoCAD drawing that is open:\n\n" + spec + "\n\n"
        "Work like this: call autocad_status first for the units; use autocad_batch_draw for more "
        "than about ten objects; put everything on named layers; then call autocad_preview and "
        "look at the picture before you tell me it is done. If Changes is off, tell me to turn it "
        "on with Changes in Settings on the Heron tab."
    )


@mcp.prompt(name="draw_detail", description="Draw a construction or installation detail the way a senior draftsman would.")
def draw_detail(subject: str, scale: str = "1:10") -> str:
    return (
        f"Draw a detail of: {subject}. Drawing scale {scale}.\n\n"
        "Work like a senior draftsman, in this order:\n"
        "1. Call autocad_status: confirm the drawing and its units. Draw in the open drawing "
        "unless asked for a new one. Set DIMSCALE and LTSCALE to the scale factor.\n"
        "2. Plan the sheet first: elevation (or section) as the main view, plan directly under "
        "it on the same centre line, notes to the right aligned with the top, labels in one "
        "column beside the main view, dimensions on the other side.\n"
        "3. Layers per discipline (structure, steel, piping, waterproofing, annotation, "
        "dimensions, hidden, centre lines).\n"
        "4. Draw each part, then turn it into a named block with autocad_make_block "
        "(e.g. 'BASE PLATE 250x250x12'). Insert repeats with autocad_insert_block, opposite "
        "hands with autocad_mirror_entities. Runs (pipe, duct, membrane) stay lines.\n"
        "5. Hatch concrete, grout and insulation; existing structure may stay loose.\n"
        "6. Labels with autocad_batch_labels (the whole column in one call; autocad_add_label "
        "for a single one) in the user's TLD style (shape 'angled' in a column, "
        "'L' for a single label): one tidy column, evenly spaced, same top-to-bottom order as "
        "the parts, short leaders, no crossings. text_align='right' for a column on the left.\n"
        "7. Dimensions: grouped, aligned, whole numbers (text_override for a rounded or "
        "described value such as '974 TO PIPE C/L').\n"
        "8. Titles: underlined view title, smaller 'SCALE " + scale + "' line under it.\n"
        "9. Notes: numbered, plain, under an underlined heading.\n"
        "10. Call autocad_preview and look as a senior draftsman: overlaps, crossings, text on "
        "lines, crowded spots, unbalanced layout. Fix them, then preview again before reporting.\n"
        "Never draw parts as loose lines. Never fake a leader with a line and a text."
    )


@mcp.prompt(name="make_sheet", description="Set up a drawing sheet end to end: layout, title block, viewport at a scale, and a saved view of what it shows.")
def make_sheet(sheet_name: str, paper_size: str = "A1", scale: str = "1:100") -> str:
    return (
        f"Set up sheet {sheet_name} on {paper_size} at {scale}.\n\n"
        "In this order, and check each step before the next:\n"
        "1. autocad_status: the drawing, its units, and whether the UCS is rotated. If it is, "
        "either work in world coordinates or say you are passing coords='ucs'.\n"
        "2. autocad_drawing_setup with the scale: it sets DIMSCALE, LTSCALE, CANNOSCALE and the "
        "text height off one number, so the sheet and the drawing agree.\n"
        f"3. autocad_create_layout name='{sheet_name}' paper_size='{paper_size}'. Read the 'sheet' "
        "it returns: 'frame' is the border, 'drawing_space' is what is left after the ISO margins "
        "and the title block strip. Lay out inside drawing_space, not up to the paper edge.\n"
        "4. autocad_page_setup for the plotter, the plot style table and the plot area.\n"
        "5. autocad_place_title_block with your own title block block or .dwg, and the attributes "
        "filled (drawing number, title, scale, date, revision). Check 'attributes_not_found' - "
        "anything listed there did not go in, so the tag name is wrong.\n"
        f"6. autocad_add_viewport at scale='{scale}', aimed with centre, corner1/corner2 or a "
        "saved view. Pass paper_centre, paper_width and paper_height to put it exactly where you "
        "want on the paper. Read 'scale_set': that is the CustomScale AutoCAD kept, so it is the "
        "proof the scale took. Lock it last.\n"
        "7. autocad_save_view for the area the viewport shows, named after the sheet. That is how "
        "the same location comes back later: autocad_list_views gives its corners, and "
        "autocad_add_viewport, autocad_export and the drawing tools all take them.\n"
        "8. autocad_preview and look at it as a draftsman: is the drawing centred in the space, "
        "clear of the title block, and is the text readable at this scale? Fix it, preview again.\n"
        "Only then report. If a step is refused, say which padlock is needed."
    )


@mcp.prompt(name="import_to_shop_drawing", description="Turn an imported IFC or CAD file into a shop drawing: proper layers, colours, details, dimensions and a sheet.")
def import_to_shop_drawing(discipline: str = "", scale: str = "1:50") -> str:
    what = f" The work is {discipline}." if discipline else ""
    return (
        "Turn what is in this drawing into a shop drawing." + what + "\n\n"
        "An imported file arrives wrong: layer names like IfcWallStandardCase or none at all, "
        "every object a hard colour instead of ByLayer, geometry at odd Z, no dimensions. Work "
        "through it in this order, and never skip the dry run:\n"
        "1. autocad_status, then autocad_list_layers with include_entity_counts=true. Say plainly "
        "what you found: how many layers, how many objects, which look like an IFC export, and "
        "how much is sitting on layer 0.\n"
        "2. autocad_remap_layers with dry_run=true first. preset='ifc' knows the usual IFC names; "
        "add your own rules for what it misses. Read 'counts' and 'unmatched_sample', show me the "
        "plan, and only then run it again with dry_run=false and set_bylayer=true.\n"
        "3. autocad_tidy_entities, again dry_run first: color_bylayer, linetype_bylayer, "
        "flatten_z for geometry off the plane, zero_thickness, off_layer_0 for the orphans, "
        "delete_empty at the end. Anything in 'failed' is usually a locked layer - unlock and "
        "repeat rather than leaving it.\n"
        f"4. autocad_drawing_setup at {scale} and autocad_create_styles for the text and dimension "
        "styles the shop drawing needs. A dimension style holds its own settings, so the drawing's "
        "DIM variables are left as they were.\n"
        "5. Now add what a shop drawing has and a model does not: section and detail marks, centre "
        "lines on every hole (autocad_add_centre_marks), hatching on cut material, welds, "
        "fixings, part marks.\n"
        "6. Dimensions with autocad_dimension_run: a chain along each face with include_overall, "
        "then baseline or ordinate where a chain would crowd. Check 'measured' against 'expected' "
        "on every row - if they differ the geometry is not where you think it is.\n"
        "7. Annotation: autocad_add_multileader for part callouts (one leader, several arrows when "
        "parts repeat), autocad_add_table for the part list or schedule, autocad_add_revision_cloud "
        "around anything changed.\n"
        "8. Then the make_sheet prompt's steps for the sheet itself, and autocad_export to PDF.\n"
        "9. autocad_check_standards at the end and report what is still off.\n"
        "Use autocad_sequence to run a settled run of steps together, like AutoLISP's progn: it "
        "checks every step's arguments before it runs the first, so a typo costs you nothing."
    )


@mcp.prompt(name="model_part", description="Model a part in 3D from a description, then take its weight and sizes off the model.")
def model_part(part: str, material: str = "steel") -> str:
    return (
        f"Model this part in 3D: {part}. Material {material}.\n\n"
        "Work the way a fabricator reads it - section first, then solid:\n"
        "1. autocad_status for the units, and autocad_get_ucs. A part is modelled on the plane you "
        "are working on, so set the UCS to that plane first with autocad_set_ucs, and remember COM "
        "only takes world coordinates: pass coords='ucs' or convert with autocad_convert_points.\n"
        "2. Draw the profile as ONE closed polyline. autocad_make_shape has the usual ones ready "
        "(steel_section, slot, rounded_rectangle, flange, gusset, bracket); autocad_batch_draw with "
        "'bulges' keeps arcs and straights in one object, which is what a region needs.\n"
        "3. autocad_extrude_profile to pull it up, with taper_angle for a draft, or revolve_angle "
        "with axis_point and axis_direction for anything turned. It closes the curves into a region "
        "itself and cleans the region up after, leaving your profile where it was.\n"
        "4. Holes, slots and cut-outs: autocad_add_solid cylinders through the part, then "
        "autocad_solid_boolean operation='subtract'. It refuses the whole call if any handle is not "
        "a solid, so a wrong handle never costs you the part. Check volume_after is less than "
        "volume_before - that is the proof the material came out.\n"
        "4b. Anything that follows a route - a duct, a pipe, a tray, a handrail - is a section "
        "swept along it: autocad_extrude_profile with path_handle, not a row of boxes.\n"
        "4c. To see inside, autocad_slice_solid cuts it with a plane given the way you would say "
        "it ('horizontally at 1500'). The two halves' volumes must add up to the original.\n"
        "4d. If this part sits among others, autocad_check_interference tells you whether it "
        "fouls them, with the overlap volume. Do that before anyone cuts metal.\n"
        "5. autocad_solid_properties for the real numbers: volume, centroid, bounding box, moments. "
        f"Multiply the volume by the density of {material} for the weight, and say which density you "
        "used.\n"
        "6. autocad_set_3d_view direction='sw_iso' visual_style='shaded' and autocad_preview to look "
        "at it. Then direction='top' with '2dwireframe' to get back to plan. For a material, "
        "autocad_list_materials first and then autocad_apply_material - only what is already in "
        "the drawing can be applied, and a material carries no density, so it never changes the "
        "weight.\n"
        "7. For anything rolled or folded from sheet, draw the flat pattern too: "
        "autocad_make_shape shape='cone_development' or 'duct_transition'. Check it with "
        "autocad_polyline_info - each arc must be exactly as long as the girth it rolls onto "
        "(pi x diameter), or the part will not meet.\n"
        "Report the sizes, the volume and the weight. Do not guess a density - if you are not sure "
        "of the material, ask."
    )


@mcp.prompt(name="shape_from_words", description="Make a drawn shape from a plain description, picked from the shape catalogue and checked after.")
def shape_from_words(description: str, scale: str = "1:10") -> str:
    return (
        f"Draw this: {description}.\n\n"
        "1. Read autocad_make_shape's catalogue and pick the shape that fits. Work out every "
        "setting from the description. If a number is not given, use the trade-standard one and say "
        "which you used - do not invent a dimension and leave it unsaid.\n"
        "2. Run it with dry_run=true first. It gives back the operations and the entity count "
        "without drawing anything, so you can see what you are about to get.\n"
        f"3. Draw it on its own named layer, at {scale}. If the shape has to sit square to "
        "something already drawn, set the UCS to that first and pass coords='ucs'.\n"
        "4. Check it with autocad_polyline_info: segment count, which segments are arcs, the "
        "radii, and the total length. A slot is one polyline with two arcs, not four objects. A "
        "flat pattern's arcs must match pi x diameter. If the numbers are wrong, say so and fix "
        "the settings - do not report it as done.\n"
        "5. Nothing in the catalogue fits? Then build it with autocad_batch_draw, using 'bulges' "
        "for the arcs so it stays one object, and say that is what you did.\n"
        "6. autocad_preview and look at it before reporting."
    )
