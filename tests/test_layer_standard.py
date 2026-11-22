"""The layer standard (#70, D-120): the rule-file format, the shipped example,
which file a call means, the CSV import, and the check and remap it feeds.

All offline: the format and the check are plain functions, the tool only reads
and writes Heron's own folder (conftest points %LOCALAPPDATA% at a temporary
folder), and the drawing is a stand-in with the same COM names.
"""

from __future__ import annotations

import asyncio
import json
import re

import pytest

from autocad_mcp.acad import layer_standard as ls
from autocad_mcp.core import gate
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import convert, standards
from autocad_mcp.tools import layer_standard as tool

HEADER = "layer,color,linetype,lineweight,plot,description,replaces,required\n"


def csv_of(*rows: str, head: str = HEADER) -> str:
    return head + "".join(row + "\n" for row in rows)


def problems(text: str) -> str:
    with pytest.raises(ls.StandardError) as caught:
        ls.from_csv(text)
    return str(caught.value)


# ---- the format ----------------------------------------------------------------


class TestOneRow:
    def test_a_full_row_is_kept_in_autocad_s_own_numbers(self):
        row = ls.parse_row({"layer": "M-HVAC-SUPP", "color": "cyan", "linetype": "Continuous", "lineweight": "0.35",
                            "plot": "yes", "description": "Supply air", "replaces": "OLD-DUCT*; MECH-SUP", "required": "y"})  # fmt: skip
        assert row == {"layer": "M-HVAC-SUPP", "pattern": False, "color": 4, "linetype": "Continuous", "lineweight": 35,
                       "plot": True, "description": "Supply air", "replaces": ["OLD-DUCT*", "MECH-SUP"], "required": True}  # fmt: skip

    def test_blank_cells_are_not_checked(self):
        assert ls.parse_row({"layer": "E-LITE", "color": "", "plot": ""}) == {
            "layer": "E-LITE", "pattern": False, "replaces": [], "required": False}  # fmt: skip

    @pytest.mark.parametrize(("given", "code"), [("25", 25), ("0.25", 25), ("0.25 mm", 25), ("Default", -3), (0.5, 50)])
    def test_a_lineweight_in_mm_or_hundredths(self, given, code):
        assert ls.parse_row({"layer": "A", "lineweight": given})["lineweight"] == code

    @pytest.mark.parametrize("given", ["ByLayer", "byblock", "0.33", "7"])
    def test_a_lineweight_a_layer_cannot_have_is_refused(self, given):
        with pytest.raises(ls.StandardError, match="lineweight"):
            ls.parse_row({"layer": "A", "lineweight": given})

    @pytest.mark.parametrize("given", ["0", "256", "bylayer", "300", "reed", "1.5"])
    def test_a_colour_a_layer_cannot_have_is_refused(self, given):
        with pytest.raises(ls.StandardError, match="colour"):
            ls.parse_row({"layer": "A", "color": given})

    def test_a_true_colour_is_refused_in_plain_words(self):
        with pytest.raises(ls.StandardError, match="true colour"):
            ls.parse_row({"layer": "A", "color": "255,0,0"})

    def test_a_name_autocad_does_not_allow_is_refused(self):
        with pytest.raises(ls.StandardError, match="does not allow"):
            ls.parse_row({"layer": "M:DUCT"})

    def test_a_pattern_row_is_a_pattern_and_cannot_be_a_target(self):
        assert ls.parse_row({"layer": "M-*-IDEN", "color": 7})["pattern"] is True
        with pytest.raises(ls.StandardError, match="nothing can be moved onto it"):
            ls.parse_row({"layer": "M-*-IDEN", "replaces": "OLD"})
        with pytest.raises(ls.StandardError, match="cannot be required"):
            ls.parse_row({"layer": "M-*", "required": "yes"})

    def test_every_wrong_cell_of_a_row_is_named_at_once(self):
        with pytest.raises(ls.StandardError) as caught:
            ls.parse_row({"layer": "X", "color": "reed", "plot": "maybe", "lineweight": "9.9"})
        message = str(caught.value)
        assert "colour 'reed'" in message and "plot 'maybe'" in message and "lineweight" in message


class TestCsv:
    def test_header_words_a_modeller_uses_are_understood(self):
        text = "Layer Name,Colour,Line Type,Line Weight (mm),Plot?,Description,Old Names,Required?\nM-A,red,HIDDEN,0.18,no,,X*,\n"
        row = ls.from_csv(text)["layers"][0]
        assert (row["color"], row["linetype"], row["lineweight"], row["plot"], row["replaces"]) == (1, "HIDDEN", 18, False, ["X*"])

    def test_excel_s_bom_and_its_windows_code_page_both_read(self, tmp_path):
        utf8 = tmp_path / "utf8.csv"
        utf8.write_bytes(b"\xef\xbb\xbf" + csv_of("M-A,1,,,,Caf\xc3\xa9,,").encode("latin-1"))
        assert ls.read_file(utf8)["layers"][0]["description"] == "Café"
        ansi = tmp_path / "ansi.csv"
        ansi.write_bytes(csv_of("M-A,1,,,,Caf\xe9,,").encode("latin-1"))
        assert ls.read_file(ansi)["layers"][0]["description"] == "Café"

    def test_a_semicolon_csv_from_a_european_excel_reads(self):
        text = "layer;color;linetype;lineweight;plot;description;replaces;required\nM-A;4;Continuous;0,35;yes;Duct;OLD-1,OLD-2;\n"
        # 0,35 is not a lineweight Heron reads; the row is reported, not guessed.
        assert "lineweight" in problems(text)
        good = ls.from_csv(text.replace("0,35", "35"))["layers"][0]
        assert good["lineweight"] == 35 and good["replaces"] == ["OLD-1", "OLD-2"]

    def test_notes_settings_and_excel_padding(self):
        text = (
            "# any note at all,,,,,,,\n"
            "# name: My office,,,,,,,\n"
            "# name_pattern: ^[A-Z]{1,2}-[A-Z]{4}$,,,,,\n"
            + HEADER + "M-DUCT,4,,,,,,\n,,,,,,,\n"
        )
        standard = ls.from_csv(text)
        assert standard["name"] == "My office"
        assert standard["name_pattern"] == "^[A-Z]{1,2}-[A-Z]{4}$"  # the commas Excel split it on, put back
        assert standard["example"] is False and len(standard["layers"]) == 1

    def test_columns_that_are_not_part_of_the_format_are_named_not_read(self):
        standard = ls.from_csv("layer,color,Remarks\nM-A,1,check with MEP lead\n")
        assert standard["ignored_columns"] == ["Remarks"]

    def test_every_problem_is_listed_with_its_row_and_nothing_is_kept(self):
        message = problems(csv_of("M-OK,1,,,,,,", "M-A,reed,,,,,,", "M-B,1,,,maybe,,,", "m-ok,2,,,,,,", "M-C,3,,,,,OLD;M-OK,"))
        assert "row 3: M-A: colour 'reed'" in message
        assert "row 4: M-B: plot 'maybe'" in message
        assert "row 5: 'm-ok' is already the layer of row 2" in message
        assert "row 6: 'M-OK' is a layer of the standard itself" in message

    def test_one_old_name_moved_two_ways_is_refused(self):
        assert "already replaced by row 2 (M-A)" in problems(csv_of("M-A,1,,,,,OLD-X,", "M-B,2,,,,,old-x,"))

    def test_a_file_with_no_header_or_no_layers_says_so(self):
        assert "needs a 'layer' column" in problems("colour,linetype\n1,HIDDEN\n")
        assert "holds no layers" in problems(HEADER)
        assert "not a regular expression" in problems("# name_pattern: ([A-Z\n" + csv_of("M-A,1,,,,,,"))

    def test_the_empty_template_is_the_format_itself(self):
        text = ls.template_csv()
        assert HEADER in text
        for column in ls.COLUMNS:
            assert f"# {column}:" in text or column in ("color", "description")
        assert "holds no layers" in problems(text)  # empty until the modeller fills it


class TestJson:
    def test_what_import_writes_reads_back_the_same(self):
        standard = ls.from_csv(csv_of("M-A,4,HIDDEN,0.25,no,Duct,OLD*,yes", "M-*-IDEN,7,,,,,,"))
        assert ls.from_json(json.loads(ls.to_json(standard))) == standard

    def test_a_hand_written_json_list_is_a_standard(self):
        standard = ls.from_json([{"layer": "E-LITE", "color": "yellow", "replaces": ["ELEC-L*"]}])
        assert standard["layers"][0]["color"] == 2

    def test_unknown_keys_and_other_formats_are_refused(self):
        with pytest.raises(ls.StandardError, match="unknown keys colour"):
            ls.from_json({"layers": [{"layer": "A", "colour": 1}]})
        with pytest.raises(ls.StandardError, match="format 2"):
            ls.from_json({"heron_layer_standard": 2, "layers": []})
        with pytest.raises(ls.StandardError, match="needs a 'layers' list"):
            ls.from_json({"rules": []})


# ---- the example that ships ----------------------------------------------------------


class TestTheExample:
    @pytest.fixture(scope="class")
    def example(self):
        return ls.read_file(ls.EXAMPLE_FILE)

    def test_it_is_marked_an_example_in_the_file_and_its_name(self, example):
        assert example["example"] is True
        assert "example" in example["name"].lower()
        first = ls.EXAMPLE_FILE.read_text(encoding="utf-8").splitlines()[0]
        assert "EXAMPLE" in first and "Not any office's standard" in first

    def test_it_covers_the_four_mep_disciplines(self, example):
        heads = ls.summary(example)["counts"]["by_first_letter"]
        for discipline in ("M", "P", "F", "E"):
            assert heads.get(discipline, 0) >= 5, discipline

    def test_every_layer_follows_its_own_name_pattern(self, example):
        pattern = re.compile(example["name_pattern"])
        for row in example["layers"]:
            if not row["pattern"]:
                assert pattern.search(row["layer"]), row["layer"]

    def test_every_listed_layer_says_how_it_looks_and_plots(self, example):
        for row in example["layers"]:
            assert {"color", "linetype", "lineweight", "plot"} <= set(row), row["layer"]
            if not row["pattern"]:
                assert row.get("description"), row["layer"]

    def test_its_linetypes_are_ones_acad_lin_has(self, example):
        assert {row["linetype"].upper() for row in example["layers"]} <= {"CONTINUOUS", "HIDDEN", "DASHED", "CENTER"}

    def test_it_requires_no_layer_so_any_mep_drawing_can_be_checked(self, example):
        assert not any(row["required"] for row in example["layers"])

    def test_it_ships_inside_the_package(self):
        assert ls.EXAMPLE_FILE.parent.name == "data" and ls.EXAMPLE_FILE.parent.parent.name == "autocad_mcp"


# ---- the check ------------------------------------------------------------------------


def layer(name, color=7, linetype="Continuous", lineweight=-3, plottable=True, **more):
    return {"name": name, "color": color, "linetype": linetype, "lineweight": lineweight, "plottable": plottable, **more}


STANDARD = ls.from_csv(
    "# name_pattern: ^[A-Z]-[A-Z]{4}\n"
    + csv_of("M-DUCT,4,Continuous,0.35,yes,Supply duct,OLD-DUCT*,", "M-*-IDEN,7,,0.18,,,,", "G-TTLB,7,,,,,,yes")
)


def found(layers, standard=STANDARD, flag_extra=True):
    return {(f["rule"], f["layer"]): f["detail"] for f in ls.check(layers, standard, flag_extra)}


class TestCheck:
    def test_a_layer_as_listed_has_no_finding(self):
        assert found([layer("m-duct", 4, "CONTINUOUS", 35, description="supply duct"), layer("G-TTLB")]) == {}

    def test_each_difference_is_named_with_both_values(self):
        detail = found([layer("M-DUCT", 3, "DASHED", 25, False, description="Old"), layer("G-TTLB")])[("layer_standard_differs", "M-DUCT")]
        for words in ("colour 3 here, 4", "linetype DASHED here, Continuous", "lineweight 0.25 mm here, 0.35 mm",
                      "does not plot here, plots", "description 'Old' here, 'Supply duct'"):  # fmt: skip
            assert words in detail

    def test_a_pattern_row_checks_the_layers_it_covers(self):
        result = ls.check([layer("M-HVAC-IDEN", 7, lineweight=25), layer("G-TTLB")], STANDARD)
        assert result[0]["rule"] == "layer_standard_differs" and result[0]["standard_row"] == "M-*-IDEN"
        assert "lineweight 0.25 mm here, 0.18 mm" in result[0]["detail"]

    def test_an_unlisted_layer_is_held_to_the_name_pattern(self):
        assert found([layer("M-PIPE"), layer("mech duct"), layer("G-TTLB")]) == {
            ("layer_standard_name", "mech duct"): "not in the layer standard, and its name does not match ^[A-Z]-[A-Z]{4}"}  # fmt: skip

    def test_without_a_name_pattern_an_unlisted_layer_is_not_in_the_standard(self):
        plain = {**STANDARD, "name_pattern": None}
        assert ("layer_not_in_layer_standard", "M-PIPE") in found([layer("M-PIPE"), layer("G-TTLB")], plain)
        assert found([layer("M-PIPE"), layer("G-TTLB")], plain, flag_extra=False) == {}

    def test_layer_0_defpoints_and_xref_layers_are_autocad_s_or_the_xref_s(self):
        plain = {**STANDARD, "name_pattern": None}
        assert found([layer("0"), layer("Defpoints"), layer("ARCH|WALLS"), layer("G-TTLB")], plain) == {}

    def test_a_required_layer_the_drawing_lacks(self):
        assert ("layer_standard_missing", "G-TTLB") in found([layer("M-DUCT", 4, lineweight=35, description="Supply duct")])

    def test_the_rule_names_are_the_ones_declared(self):
        plain = {**STANDARD, "name_pattern": None}
        rules = {f["rule"] for f in ls.check([layer("M-DUCT"), layer("X")], plain)}
        rules |= {f["rule"] for f in ls.check([layer("x y")], STANDARD)}
        assert rules == set(ls.RULES)


# ---- the remap rules ---------------------------------------------------------------------


class TestRemapRules:
    def test_standard_layers_stay_and_old_names_move(self):
        rules = ls.remap_rules(STANDARD)
        assert rules[0] == {"source_layer": "M-DUCT", "layer": "M-DUCT", "color": 4, "linetype": "Continuous",
                            "lineweight": 35, "plot": True, "description": "Supply duct"}  # fmt: skip
        assert rules[-1]["source_layer"] == "OLD-DUCT*" and rules[-1]["layer"] == "M-DUCT"
        assert all(rule["layer"] != "M-*-IDEN" for rule in rules)  # a pattern is never a target
        objects = [
            {"handle": "1", "type": "line", "layer": "M-DUCT"},
            {"handle": "2", "type": "line", "layer": "old-duct-supply"},
            {"handle": "3", "type": "block", "layer": "A-WALL", "block_name": "OLD-DUCT-FAN"},
        ]
        plan = convert.plan_remap(objects, convert.validate_rules(rules))
        assert [(m["handle"], m["to"]) for m in plan["moves"]] == [("2", "M-DUCT")]
        assert plan["counts"]["already_right"] == 1 and plan["unmatched"] == ["3"]  # a block's name is not a layer
        assert plan["layers"]["M-DUCT"]["color"] == 4

    def test_a_layer_name_with_a_bracket_is_matched_as_written(self):
        standard = ls.from_csv(csv_of("M-[A],1,,,,,OLD[1],"))
        rules = convert.validate_rules(ls.remap_rules(standard))
        assert convert.rule_hits({"layer": "M-[A]"}, rules[0]) and not convert.rule_hits({"layer": "M-A"}, rules[0])
        assert convert.rule_hits({"layer": "old[1]"}, rules[1])

    def test_the_example_s_rules_are_valid_remap_rules(self):
        rules = convert.validate_rules(ls.remap_rules(ls.read_file(ls.EXAMPLE_FILE)))
        assert len(rules) > 40


# ---- which file a call means ----------------------------------------------------------------


def write_office(text: str) -> None:
    tool.template_file().parent.mkdir(parents=True, exist_ok=True)
    tool.template_file().write_text(text, encoding="utf-8")
    tool._import(None)


class TestWhichStandard:
    def test_office_with_nothing_loaded_is_the_example_said_plainly(self):
        standard, info = tool.resolve("office")
        assert standard["example"] and info["fallback"] and info["kind"] == "example"
        assert "because no office layer standard is loaded" in info["source"]

    def test_the_office_file_on_this_pc_wins_over_the_example(self, tmp_path):
        write_office(csv_of("M-OFFICE,1,,,,,,"))
        standard, info = tool.resolve("office")
        assert info["kind"] == "office" and not info.get("fallback")
        assert [row["layer"] for row in standard["layers"]] == ["M-OFFICE"]
        assert tool.office_file().is_relative_to(tmp_path)  # %LOCALAPPDATA%, never the repository

    def test_a_file_the_modeller_names_wins_for_that_call(self, tmp_path):
        write_office(csv_of("M-OFFICE,1,,,,,,"))
        named = tmp_path / "job layers.csv"
        named.write_text(csv_of("M-JOB,2,,,,,,"), encoding="utf-8")
        standard, info = tool.resolve(f'"{named}"')
        assert info["kind"] == "file" and standard["layers"][0]["layer"] == "M-JOB"

    def test_example_always_means_the_shipped_one(self):
        write_office(csv_of("M-OFFICE,1,,,,,,"))
        standard, info = tool.resolve("Example")
        assert info["kind"] == "example" and standard["example"] and not info.get("fallback")

    def test_a_relative_or_missing_path_is_refused(self, tmp_path):
        with pytest.raises(Exception, match="full path"):
            tool.resolve("layers.csv")
        with pytest.raises(Exception, match="There is no layer standard"):
            tool.resolve(str(tmp_path / "nope.csv"))

    def test_a_broken_office_file_is_an_error_never_the_example(self):
        tool.office_file().parent.mkdir(parents=True, exist_ok=True)
        tool.office_file().write_text("{not json", encoding="utf-8")
        with pytest.raises(Exception, match="not valid JSON"):
            tool.resolve("office")


# ---- the tool ---------------------------------------------------------------------------------


def call(**kw):
    return asyncio.run(tool.autocad_layer_standard(**kw))


def answer(**kw):
    text = call(**kw)
    assert not text.startswith("Error:"), text
    return json.loads(text)


class TestTheTool:
    def test_it_is_a_read_tool_that_needs_no_autocad(self, monkeypatch):
        assert risk_of("autocad_layer_standard") is Risk.READ
        assert "autocad_layer_standard" in gate.NO_AUTOCAD_TOOLS
        monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "on")
        gate.reset()
        assert answer(action="show")["office_standard"] is None

    def test_template_fill_import_show_remove(self):
        shown = answer()
        assert "no office layer standard" in shown["in_force"] and "action='template'" in shown["next"]
        made = answer(action="template")
        assert made["template"] == str(tool.template_file())
        assert "already a CSV to fill" in call(action="template")
        with tool.template_file().open("a", encoding="utf-8") as fh:
            fh.write("M-HVAC-SUPP,4,Continuous,0.35,yes,Supply duct,MECH-SUP*,\nP-DOMW-CWTR,5,,,,,,\n")
        loaded = answer(action="import")
        assert loaded["standard"]["counts"]["layers"] == 2 and loaded["imported"] == str(tool.office_file())
        kept = json.loads(tool.office_file().read_text(encoding="utf-8"))
        assert kept["imported_from"] == str(tool.template_file()) and kept["layers"][0]["lineweight"] == 35
        shown = answer(action="show")
        assert shown["office_standard"] == str(tool.office_file()) and shown["imported_from"]
        gone = answer(action="remove")
        assert gone["kept_as"].endswith(tool.PREVIOUS_FILE) and not tool.office_file().exists()
        assert answer(action="show")["office_standard"] is None

    def test_a_csv_with_a_problem_imports_nothing(self, tmp_path):
        write_office(csv_of("M-GOOD,1,,,,,,"))
        bad = tmp_path / "bad.csv"
        bad.write_text(csv_of("M-NEW,1,,,,,,", "M-X,pink,,,,,,"), encoding="utf-8")
        refused = call(action="import", path=str(bad))
        assert refused.startswith("Error:") and "row 3: M-X: colour 'pink'" in refused
        assert json.loads(tool.office_file().read_text(encoding="utf-8"))["layers"][0]["layer"] == "M-GOOD"

    def test_show_with_a_path_checks_a_csv_without_importing_it(self, tmp_path):
        mine = tmp_path / "mine.csv"
        mine.write_text(csv_of("M-A,1,,,,,,"), encoding="utf-8")
        assert answer(action="show", path=str(mine))["standard"]["counts"]["layers"] == 1
        assert not tool.office_file().exists()

    def test_the_example_is_never_imported_as_the_office_s(self):
        refused = call(action="import", path=str(ls.EXAMPLE_FILE))
        assert refused.startswith("Error:") and "says it is an example" in refused and not tool.office_file().exists()

    def test_a_second_import_keeps_the_first_as_previous(self, tmp_path):
        write_office(csv_of("M-FIRST,1,,,,,,"))
        second = tmp_path / "second.csv"
        second.write_text(csv_of("M-SECOND,1,,,,,,"), encoding="utf-8")
        assert answer(action="import", path=str(second))["previous"].endswith(tool.PREVIOUS_FILE)
        previous = json.loads(tool.office_file().with_name(tool.PREVIOUS_FILE).read_text(encoding="utf-8"))
        assert previous["layers"][0]["layer"] == "M-FIRST"

    def test_import_with_no_template_says_where_to_start(self):
        refused = call(action="import")
        assert refused.startswith("Error:") and "action='template'" in refused


# ---- the check and the remap tools with a layer standard ---------------------------------------


class Item:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Collection:
    def __init__(self, items):
        self._items = items
        self.Count = len(items)

    def Item(self, i):
        return self._items[i]


async def _direct(fn):
    return fn()


@pytest.fixture
def drawing(monkeypatch):
    layers = [("0", 7, "Continuous", -3, ""), ("M-HVAC-SUPP", 4, "Continuous", 35, "Supply air ductwork"),
              ("M-HVAC-RETN", 1, "Continuous", 35, "Return air ductwork"), ("mech stuff", 7, "Continuous", -3, "")]  # fmt: skip
    doc = Item(Layers=Collection([Item(Name=n, Color=c, Linetype=lt, Lineweight=lw, Description=d, LayerOn=True,
                                       Freeze=False, Lock=False, Plottable=True) for n, c, lt, lw, d in layers]))  # fmt: skip
    monkeypatch.setattr(standards, "run", _direct)
    monkeypatch.setattr(standards, "get_doc", lambda: doc)
    return doc


def check(**kw):
    text = asyncio.run(standards.autocad_check_standards(**kw))
    assert not text.startswith("Error:"), text
    return json.loads(text)


class TestCheckStandards:
    def test_against_the_example_by_name(self, drawing):
        report = check(layer_standard="example")
        assert report["passed"] is False and report["layer_standard"]["example"] is True
        assert "not an office's standard" in report["layer_standard"]["note"]
        assert report["summary"] == {"layer_standard_differs": 1, "layer_standard_name": 1}
        differs = [f for f in report["findings"] if f["rule"] == "layer_standard_differs"][0]
        assert differs["layer"] == "M-HVAC-RETN" and "colour 1 here, 3" in differs["detail"]
        assert "generic MEP example" in report["source"]

    def test_office_with_none_loaded_is_not_decided(self, drawing, monkeypatch):
        report = check(layer_standard="office")
        assert report["passed"] is None and "action='template'" in report["layer_standard"]["warning"]
        assert report["findings"]  # still shown: what the example would say

    def test_office_with_none_loaded_and_a_failing_rule_still_fails(self, drawing):
        report = check(layer_standard="office", rules={"layers": {"G-TTLB": {}}})
        assert report["passed"] is False and report["summary"]["layer_missing"] == 1

    def test_against_the_office_standard_loaded_here(self, drawing):
        write_office(csv_of("M-HVAC-SUPP,4,Continuous,0.35,yes,,,", "M-HVAC-RETN,1,Continuous,0.35,yes,,,", "mech stuff,7,,,,,,"))
        report = check(layer_standard="office")
        assert report["passed"] is True and report["layer_standard"]["example"] is False
        assert report["source"].startswith("the office layer standard on this PC")
        assert "layer_standard" in report["checked"]

    def test_nothing_given_still_asks_for_something(self, drawing):
        assert "layer_standard" in asyncio.run(standards.autocad_check_standards())


class TestRemapLayers:
    @pytest.fixture
    def imported(self, monkeypatch):
        rows = [{"handle": "1", "type": "line", "layer": "MECH-SUPPLY-OLD", "color": 7, "linetype": "Continuous"},
                {"handle": "2", "type": "line", "layer": "M-HVAC-SUPP", "color": 7, "linetype": "Continuous"}]  # fmt: skip
        monkeypatch.setattr(convert, "run", _direct)
        monkeypatch.setattr(convert, "get_doc", lambda: object())
        monkeypatch.setattr(convert, "require_idle", lambda doc: None)
        monkeypatch.setattr(convert, "_gather", lambda *a, **k: (rows, {}, False))

    def test_office_with_none_loaded_is_refused_and_moves_nothing(self, imported):
        refused = asyncio.run(convert.autocad_remap_layers(layer_standard="office", dry_run=True))
        assert refused.startswith("Error:") and "Nothing was moved" in refused and "layer_standard='example'" in refused

    def test_the_example_plans_old_names_onto_its_layers(self, imported):
        plan = json.loads(asyncio.run(convert.autocad_remap_layers(layer_standard="example", dry_run=True)))
        assert plan["counts"]["to_move"] == 1 and plan["moves_sample"][0]["to"] == "M-HVAC-SUPP"
        layers = {row["name"]: row for row in plan["layers"]}
        assert layers["M-HVAC-SUPP"]["color"] == 4 and layers["M-HVAC-SUPP"]["lineweight"] == 35

    def test_the_office_standard_loaded_here(self, imported):
        write_office(csv_of("M-HVAC-SUPP,4,Continuous,0.35,yes,,MECH-SUPPLY*,"))
        plan = json.loads(asyncio.run(convert.autocad_remap_layers(layer_standard="office", dry_run=True)))
        assert plan["counts"] == {"read": 2, "to_move": 1, "already_right": 1, "unmatched": 0, "layers_wanted": 1}
