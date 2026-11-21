"""Can the right tool actually be found, in a modeller's own words?

Ajmal's doubt, in his words: *"still, I have doubt that it will find
everything fast."* He was right to doubt it - the first version put the right
tool first on 36 of 55 phrases and missed six altogether. This file is how
that stopped being an opinion. It now stands at 88 of 101 first and 101 of 101
in the top three, over all 138 tools, scored the way autocad://tools/find
ranks them: a plain question gets the tools that only read first (D-67).

**These phrases are our own**, so the score is a floor on a sample, not a
promise about every phrase anyone will ever type. What it does catch is
regression: rename a tool, reword a "Use when" line, or add a tool that
steals a common word, and the number drops here before it costs anyone time
at the machine.

When a phrase misses, the fix is almost always the **tool's own `Use when`
line**, not the scoring. That is how `autocad_drawing_setup` came to say
DIMSCALE out loud: this test showed it did not.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.acad.findtool import Entry, is_question, rank, search, split_bullets
from autocad_mcp.core.registry import mcp
from autocad_mcp.core.risk import RISK, Risk
from autocad_mcp.tools import register_all, resources

register_all()

# The floors. Current, over 138 tools: 88 of these put the right tool first
# and all 101 find it in the top three. Set a little under, so ordinary
# rewording does not fail the build but a real loss does. The top-three floor
# is deliberately the full count minus one: a phrase that stops finding its
# tool at all is the failure that costs someone time at the machine.
FIRST_PLACE_FLOOR = 83
TOP_THREE_FLOOR = 100


CASES = [
    ("how many metres of DN50 pipe on this layer", "autocad_total_length"),
    ("how many diffusers on this floor", "autocad_count_blocks"),
    ("how many DN50 are written on the drawing", "autocad_count_text"),
    ("give me the camera schedule as a table", "autocad_add_table"),
    ("pull the tag values out for a schedule", "autocad_extract_attributes"),
    ("I need the flat pattern for a 200 to 100 reducer", "autocad_make_shape"),
    ("draw a 200 flange with 8 bolt holes", "autocad_make_shape"),
    ("draw a 120 x 40 slot with round ends", "autocad_make_shape"),
    ("convert this IFC import to proper layers", "autocad_remap_layers"),
    ("everything is on layer 0 and hard colours, tidy it", "autocad_tidy_entities"),
    ("does this drawing follow our layer standard", "autocad_check_standards"),
    ("check this drawing before I issue it", "autocad_checklist"),
    ("run our office check list", "autocad_checklist"),
    ("save the check results as excel to send with the drawings", "autocad_checklist_report"),
    ("make an excel report of the checks", "autocad_checklist_report"),
    ("make an A1 sheet at 1 to 100", "autocad_create_layout"),
    ("put the title block on every sheet", "autocad_place_title_block"),
    ("add a viewport showing the plan at 1 to 50", "autocad_add_viewport"),
    ("set all 42 sheets to A1 monochrome", "autocad_page_setup"),
    ("plot this to PDF", "autocad_export"),
    ("save this area so I can come back to it", "autocad_save_view"),
    ("the UCS is rotated, what are the real world coordinates", "autocad_convert_points"),
    ("line the UCS up with that block", "autocad_set_ucs"),
    ("set DIMSCALE and LTSCALE for 1 to 50", "autocad_drawing_setup"),
    ("make a dimension style for the shop drawing", "autocad_create_styles"),
    ("make a multileader style for 1:50 labels", "autocad_create_styles"),
    ("create a table style for the equipment schedule", "autocad_create_styles"),
    ("dimension along that wall as a chain", "autocad_dimension_run"),
    ("put centre crosses on all the holes", "autocad_add_centre_marks"),
    ("one note pointing at three bolts", "autocad_add_multileader"),
    ("cloud the bit that changed", "autocad_add_revision_cloud"),
    ("run these five steps together like progn", "autocad_sequence"),
    ("draw 300 objects at once", "autocad_batch_draw"),
    ("turn these lines into a block", "autocad_make_block"),
    ("put a camera block at 4500,2300", "autocad_insert_block"),
    ("hangers every 2 m along that duct", "autocad_place_along"),
    ("place all the cameras from this csv", "autocad_place_from_csv"),
    ("number these cameras CAM-001 upwards", "autocad_number_tags"),
    ("change every REV A to REV B", "autocad_find_replace_text"),
    ("fill the title block attributes", "autocad_set_attributes"),
    ("select the whole pipe run from one line", "autocad_select_connected"),
    ("is that slot one object and what is its perimeter", "autocad_polyline_info"),
    ("hatch that slab as concrete", "autocad_add_hatch"),
    ("give me a parallel line 200 inside", "autocad_offset_entities"),
    ("extrude this profile 200 up", "autocad_extrude_profile"),
    ("make a box 2400 x 1200 x 200", "autocad_add_solid"),
    ("subtract these holes from the plate", "autocad_solid_boolean"),
    ("what is the volume and centroid of that solid", "autocad_solid_properties"),
    ("show me the model from the south west", "autocad_set_3d_view"),
    ("draw a helix for a spiral stair", "autocad_draw_3d_path"),
    ("let me see what I drew", "autocad_preview"),
    ("what units is this drawing in", "autocad_status"),
    ("what layers are in here", "autocad_list_layers"),
    ("how big is the drawing overall", "autocad_get_extents"),
    ("bring the title block in from our template", "autocad_import_from_drawing"),
    ("text pasted from Word keeps its own font", "autocad_text_clean"),
    ("the sheets are out of order, renumber them", "autocad_manage_layouts"),
    ("tidy that column of labels so they line up", "autocad_align_text"),
    ("label all the parts of this detail in one go", "autocad_batch_labels"),
    ("check the drawing database for errors", "autocad_audit"),
    ("what is DIMSCALE set to", "autocad_get_variable"),
    ("which drawings are open", "autocad_list_drawings"),
    # The 3D side, added after the first run of this test. A new tool that
    # cannot be found is a new tool nobody uses.
    ("does the ductwork clash with the steel", "autocad_check_interference"),
    ("check for clashes between these two sets", "autocad_check_interference"),
    ("section that model at 1500 above floor level", "autocad_slice_solid"),
    ("cut this fitting in half so I can see the bore", "autocad_slice_solid"),
    ("lift that whole frame 3500 up", "autocad_transform_3d"),
    ("tip that brace 30 degrees about the X axis", "autocad_transform_3d"),
    ("copy this floor up 12 times at 3600", "autocad_transform_3d"),
    ("what materials does this drawing have", "autocad_list_materials"),
    ("make those beams look like steel", "autocad_apply_material"),
    # autocad_render was removed (D-87, #158): a render is set up, then the modeller presses Render.
    ("render this view for the client", "autocad_add_camera_view"),
    ("run that duct section along the route I drew", "autocad_extrude_profile"),
    ("a 400 x 200 oval duct standing up", "autocad_add_solid"),
    # The drafting objects added on 2026-10-28.
    ("draw a spline through these points", "autocad_draw_spline"),
    ("draw a flexible duct curve from the grille to the diffuser", "autocad_draw_spline"),
    ("draw a 200 mm wall with a multiline", "autocad_draw_multiline"),
    ("mline double line wall along these points", "autocad_draw_multiline"),
    ("mask the hatch behind this tag with a wipeout", "autocad_add_wipeout"),
    ("hide the wipeout frames", "autocad_add_wipeout"),
    ("xref the architect's plan in at 0,0", "autocad_attach_xref"),
    ("reload the xref after the new revision", "autocad_manage_xref"),
    ("bind the xrefs before issue", "autocad_manage_xref"),
    ("make a custom hatch pattern pat file for insulation", "autocad_create_hatch_pattern"),
    ("create a CHWS linetype with the text in the line", "autocad_create_linetype"),
    ("make a dash dot linetype lin file", "autocad_create_linetype"),
    # The 3D edits and super hatch the plug-in does itself (2026-10-29).
    ("number the edges of this solid so I can pick them", "autocad_list_solid_faces_and_edges"),
    ("make a transition from the rectangular duct to the round one", "autocad_loft"),
    ("loft these sections into a solid", "autocad_loft"),
    ("round the upright edges of the plinth", "autocad_fillet_solid_edges"),
    ("fillet the edges of this 3D block 5 mm", "autocad_fillet_solid_edges"),
    ("chamfer the top edges of the base plate", "autocad_chamfer_solid_edges"),
    ("make this box an open top tank with 10 mm walls", "autocad_shell_solid"),
    ("pull the top face of the plinth up 150", "autocad_press_pull_faces"),
    ("thicken this roof surface", "autocad_thicken_surface"),
    ("fill the terrace with the paver block like a hatch", "autocad_super_hatch"),
    ("superhatch this area with a block", "autocad_super_hatch"),
    # Lights and materials for a render (2026-11-05).
    ("put a warm white LED downlight over the dining table", "autocad_add_light"),
    ("add an IES web light for the bedroom", "autocad_add_light"),
    ("make a laterite stone material for the wall", "autocad_create_material"),
    ("make the cove LED strip glow in the night render", "autocad_create_material"),
    ("make a walnut veneer material with the grain at 1 m", "autocad_create_material"),
    ("save this 3D angle as a camera view for the render", "autocad_save_view"),
    # The round trip, the folder check and the companion page (2026-11-21).
    ("give me the equipment tags in Excel so I can fill them in", "autocad_export_attribute_sheet"),
    ("I filled in the tags in the Excel, put them back in the drawing", "autocad_apply_attribute_sheet"),
    ("check every drawing in the issue folder before we send it", "autocad_check_folder"),
    ("show me what you are doing in a window beside AutoCAD", "autocad_companion"),
    # Layers and annotation (D-80, D-81).
    ("save the layers as they are now as a layer state", "autocad_layer_states"),
    ("put the layers back to the ISSUE layer state", "autocad_layer_states"),
    ("isolate the duct layers", "autocad_isolate_layers"),
    ("bring all the layers back after isolating", "autocad_isolate_layers"),
    ("merge the old duct layer into M-DUCT", "autocad_merge_layers"),
    ("space these stacked dimensions evenly", "autocad_space_dimensions"),
    ("break the dimensions where the pipes cross them", "autocad_break_dimensions"),
    ("add the 1:100 scale to these notes", "autocad_annotation_scales"),
    ("which annotation scales does this note have", "autocad_list_annotation_scales"),
    # Setting a render up (2026-11-21, #59-#63): none of these renders.
    ("put a camera in the living room corner with a 24 mm lens", "autocad_add_camera_view"),
    ("set the sun for Doha at 10 in the morning on 21 June", "autocad_set_sun"),
    ("which lights are on in the villa", "autocad_list_lights"),
    ("night render: sun off and all the downlights on", "autocad_switch_lights"),
    ("the render is too dark, change the exposure", "autocad_set_render_exposure"),
    # Blocks, attributes and tables (D-82, D-83; issues #115, #117, #106).
    ("make a tag block with a TAG attribute", "autocad_make_block"),
    ("I added an attribute to the block, update all the inserts", "autocad_sync_attributes"),
    ("attsync the title block", "autocad_sync_attributes"),
    ("put the pump schedule from the Excel file on the sheet", "autocad_table_from_excel"),
    ("the schedule changed in excel, update the table", "autocad_update_table_links"),
    ("change the value in cell B3 of that table", "autocad_set_table_cells"),
    ("copy the pump skid from the other open drawing into this one", "autocad_copy_from_drawing"),
]

def entries() -> list[Entry]:
    """Every tool as the search sees it, from the live index."""
    index = json.loads(asyncio.run(resources.tool_index()))
    rows = []
    for group in index["padlocks"].values():
        for row in group["tools"]:
            use, avoid = split_bullets(row["use_when"])
            rows.append(Entry(row["tool"], row["title"], row["summary"], use, avoid))
    return rows


ENTRIES = entries()


def reads(tool: str) -> bool:
    return RISK.get(tool) is Risk.READ


def found(phrase: str, limit: int = 3) -> list[str]:
    """The tools autocad://tools/find puts first: a question gets the reading ones first."""
    return [hit.tool for hit in rank(ENTRIES, phrase, limit=limit, reads=reads)]


# Plain questions (issue #90, D-67): each must get a tool that only reads
# first, and the expected one in the top three. Several of these put a change
# tool first before question mode: "is that polyline closed" got
# autocad_draw_polyline, "how big is that solid" autocad_add_solid.
QUESTION_CASES = [
    ("how many sheets does this drawing have", "autocad_list_layouts"),
    ("how long is the pipe on the CHW layer", "autocad_total_length"),
    ("what is the area of that room polyline", "autocad_polyline_info"),
    ("which blocks are in this drawing", "autocad_list_blocks"),
    ("is there any text on layer 0", "autocad_count_text"),
    ("are there any xrefs in this drawing", "autocad_xref_tree"),
    ("what is the current UCS", "autocad_get_ucs"),
    ("what is LTSCALE set to", "autocad_get_variable"),
    ("is that polyline closed", "autocad_polyline_info"),
    ("how big is that solid", "autocad_solid_properties"),
    ("what layers are frozen", "autocad_list_layers"),
    ("what did you draw in this chat", "autocad_activity"),
    ("what keeps failing this week", "autocad_gaps"),
]

# Not questions: each asks for a job, so question mode must leave it alone.
NOT_QUESTIONS = [
    "how do I draw a flange",
    "can you plot this to PDF",
    "does the ductwork clash with the steel",
    "draw a polyline round the room",
    "what if I move the duct up 200",
]


class TestItFindsTheRightTool:
    def test_the_right_tool_is_usually_first(self):
        wins = [phrase for phrase, want in CASES if found(phrase)[:1] == [want]]
        assert len(wins) >= FIRST_PLACE_FLOOR, (
            f"only {len(wins)}/{len(CASES)} phrases put the right tool first "
            f"(floor {FIRST_PLACE_FLOOR}). Misses: "
            f"{[p for p, w in CASES if found(p)[:1] != [w]]}"
        )

    def test_the_right_tool_is_nearly_always_in_the_top_three(self):
        wins = [phrase for phrase, want in CASES if want in found(phrase)]
        assert len(wins) >= TOP_THREE_FLOOR, (
            f"only {len(wins)}/{len(CASES)} phrases found the right tool at all "
            f"(floor {TOP_THREE_FLOOR}). Misses: "
            f"{[(p, w, found(p)) for p, w in CASES if w not in found(p)]}"
        )

    @pytest.mark.parametrize("phrase,want", CASES)
    def test_every_phrase_finds_something(self, phrase, want):
        """A phrase that returns nothing is a hole, whatever the hit rate."""
        assert found(phrase), f"{phrase!r} matched no tool at all"

    @pytest.mark.parametrize("phrase,want", CASES)
    def test_every_expected_tool_is_a_real_tool(self, phrase, want):
        assert want in {entry.tool for entry in ENTRIES}, f"{want} is not a registered tool"


class TestTheSearchBehaves:
    def test_it_is_not_fooled_by_a_dont_use_when(self):
        """autocad_set_variable names autocad_drawing_setup only to send you there."""
        hits = search(ENTRIES, "set DIMSCALE and LTSCALE for 1 to 50", limit=3)
        assert "autocad_drawing_setup" in [h.tool for h in hits]

    def test_a_rare_word_beats_a_common_one(self):
        """"flange" is in one tool; "draw" is in nine names."""
        assert found("draw a flange")[0] == "autocad_make_shape"

    def test_the_same_phrase_always_gives_the_same_answer(self):
        once = found("how many metres of pipe", limit=5)
        assert once == found("how many metres of pipe", limit=5)

    def test_nonsense_finds_nothing_rather_than_guessing(self):
        assert search(ENTRIES, "qqqq zzzz", limit=3) == []

    def test_filler_alone_finds_nothing(self):
        assert search(ENTRIES, "the and of in a to", limit=3) == []

    def test_it_says_which_words_matched(self):
        hit = search(ENTRIES, "flat pattern for a reducer", limit=1)[0]
        assert hit.matched, "a hit with no matched words cannot be debugged"

    def test_a_better_match_scores_clearly_higher(self):
        """Close scores mean the ranking is luck. The winner should be clear."""
        hits = search(ENTRIES, "how many metres of DN50 pipe on this layer", limit=2)
        assert hits[0].score > hits[1].score * 1.5


class TestTheResourceAnswers:
    def test_it_is_registered_as_a_template(self):
        templates = asyncio.run(mcp.list_resource_templates())
        assert "autocad://tools/find/{phrase}" in [t.uri_template for t in templates]

    def test_it_answers_with_padlocks_and_reasons(self):
        out = json.loads(asyncio.run(resources.find_tool("flat pattern for a reducer")))
        assert out["matches"], out
        first = out["matches"][0]
        assert first["tool"] == "autocad_make_shape"
        assert first["needs"] == "Changes"
        assert first["summary"] and first["use_when"] and first["matched_words"]

    def test_it_returns_nothing_rather_than_noise(self):
        out = json.loads(asyncio.run(resources.find_tool("qqqq zzzz")))
        assert out["count"] == 0
        assert "autocad://tools" in out["note"]

    def test_it_needs_no_autocad(self):
        """Like the index, it reads no drawing, so it is not gated."""
        out = json.loads(asyncio.run(resources.find_tool("what units is this drawing in")))
        assert out["matches"]


class TestAPlainQuestionNeverGetsAChangeToolFirst:
    """Issue #90: "how many...", "what is...", "is there..." get a tool that only reads first."""

    @pytest.mark.parametrize("phrase,want", QUESTION_CASES)
    def test_it_reads_as_a_question(self, phrase, want):
        assert is_question(phrase)

    @pytest.mark.parametrize("phrase,want", QUESTION_CASES)
    def test_a_reading_tool_comes_first_and_the_right_one_is_near(self, phrase, want):
        top = found(phrase)
        assert top and reads(top[0]), f"{phrase!r} got {top}"
        assert want in top, f"{phrase!r} wanted {want}, got {top}"

    @pytest.mark.parametrize("phrase", NOT_QUESTIONS)
    def test_a_job_is_not_mistaken_for_a_question(self, phrase):
        assert not is_question(phrase)

    def test_every_measured_question_gets_a_reading_tool_first(self):
        asked = [p for p, _ in CASES + QUESTION_CASES if is_question(p)]
        assert len(asked) >= 20
        wrong = [(p, found(p)[:1]) for p in asked if not reads(found(p)[0])]
        assert not wrong, wrong

    def test_the_raw_search_alone_would_have_put_a_change_tool_first(self):
        """The proof the rule does something: without it, these answer a question with a change."""
        assert search(ENTRIES, "is that polyline closed", limit=1)[0].tool == "autocad_draw_polyline"
        assert found("is that polyline closed")[0] == "autocad_polyline_info"

    def test_the_resource_offers_only_reading_tools_for_a_question(self):
        out = json.loads(asyncio.run(resources.find_tool("is there a clash between the duct and the steel")))
        assert out["question"] is True
        assert all(reads(m["tool"]) for m in out["matches"]), out["matches"]
        apart = [m["tool"] for m in out["would_change_the_drawing"]]
        assert "autocad_check_interference" in apart
        assert "would_change_the_drawing" in out["note"]

    def test_the_resource_leaves_a_job_alone(self):
        out = json.loads(asyncio.run(resources.find_tool("draw a 200 flange with 8 bolt holes")))
        assert out["question"] is False
        assert out["matches"][0]["tool"] == "autocad_make_shape"
        assert "would_change_the_drawing" not in out
