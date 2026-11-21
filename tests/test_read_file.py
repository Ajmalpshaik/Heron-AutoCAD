"""Reading DXF / DWG files with AutoCAD closed (#71) and the standards check against
a reference drawing (#69), D-92. No AutoCAD: the DXF files are made here with ezdxf.

What is proved offline: the DXF reader itself (layers, blocks and counts, text,
attributes, extents, styles), the refusals in plain words, finding the ODA File
Converter and the way it is called, and the compare. What needs a real PC
(the converter on a real DWG, AutoCAD's ObjectDBX on a .dws) is in
docs/NEEDS-CHECKING.md Group AG, NOT RUN.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import ezdxf
import pytest

from autocad_mcp.acad import dxf_file, standard_compare, why
from autocad_mcp.acad.checklist import PASS_MEANS
from autocad_mcp.core import gate
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.core.risk import RISK, Risk, risk_of
from autocad_mcp.tools import files, standards


def make_dxf(path: Path) -> Path:
    """A small MEP drawing: layers, a block with an attribute, text, a layout, a nested block."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    doc.linetypes.add("DASHED", pattern=[0.6, 0.5, -0.1], description="Dashed __ __ __")
    doc.layers.add("M-DUCT", color=3, linetype="DASHED")
    doc.layers.add("M-TEXT", color=1)
    doc.layers.add("M-HIDDEN", color=8).dxf.plot = 0
    valve = doc.blocks.new("VALVE")
    valve.add_line((0, 0), (10, 0))
    valve.add_attdef("TAG", (0, 5), dxfattribs={"height": 2.5})
    skid = doc.blocks.new("PUMP-SKID")
    skid.add_blockref("VALVE", (0, 0))
    msp = doc.modelspace()
    msp.add_line((0, 0), (5000, 3000), dxfattribs={"layer": "M-DUCT"})
    for i in range(3):
        ref = msp.add_blockref("VALVE", (i * 100, 0), dxfattribs={"layer": "M-DUCT"})
        ref.add_auto_attribs({"TAG": f"V-{i + 1}"})
    msp.add_blockref("PUMP-SKID", (900, 900))
    msp.add_text("FCU-03", dxfattribs={"layer": "M-TEXT", "height": 2.5}).set_placement((10, 10))
    msp.add_mtext("Supply AIR duct", dxfattribs={"layer": "M-TEXT", "char_height": 3.5})
    doc.layouts.get("Layout1").add_text("SHEET M-101", dxfattribs={"height": 5})
    doc.add_xref_def("base-plan.dwg", "BASE")
    doc.saveas(path)
    return path


@pytest.fixture
def drawing(tmp_path):
    return make_dxf(tmp_path / "M-101.dxf")


def read(path, what="summary", **kw):
    args = {"layer": None, "block_name": None, "contains": None, "max_items": 500, "output": "json", **kw}
    return files.read(str(path), what, args["layer"], args["block_name"], args["contains"], args["max_items"], args["output"])


# ---- the reader -------------------------------------------------------------


def test_the_summary_gives_version_units_extents_and_counts(drawing):
    answer = read(drawing)
    assert answer["format"] == "DXF R2018 (AC1032)" and answer["units"] == "millimeters"
    assert answer["extents"]["max"][:2] == [5000.0, 3000.0] and "worked out" in answer["extents"]["from"]
    assert answer["objects"]["model"] == 7 and answer["objects"]["layouts"] == {"Layout1": 1}
    assert answer["model_by_type"]["INSERT"] == 4 and answer["text"] == 3
    assert answer["most_placed_blocks"][0] == {"name": "VALVE", "placed": 3}
    assert answer["layouts"] == ["Layout1"]
    assert answer["xrefs"] == [{"name": "BASE", "path": "base-plan.dwg", "found": False}]
    assert answer["read_by"].startswith("ezdxf") and answer["note"] == dxf_file.SAVED_ONLY


def test_extents_saved_in_the_header_are_used():
    doc = ezdxf.new()  # as AutoCAD saves a file: real values in the header
    doc.header["$EXTMIN"], doc.header["$EXTMAX"] = (0, 0, 0), (100, 50, 0)
    assert dxf_file.extents(doc) == {"min": [0.0, 0.0, 0.0], "max": [100.0, 50.0, 0.0],
                                     "from": "the file's header, as AutoCAD last saved it"}  # fmt: skip


def test_header_extents_from_the_origin_are_used():
    doc = ezdxf.new()
    doc.header["$EXTMIN"], doc.header["$EXTMAX"] = (0, 0, 0), (0, 0, 0)  # a Vec3 of zeros is falsy
    assert dxf_file.extents(doc)["from"] == "the file's header, as AutoCAD last saved it"


def test_an_odd_file_name_never_reaches_the_converter(drawing, tmp_path, monkeypatch):
    source = tmp_path / "M-101 [Rev A];2.dwg"
    source.write_bytes(b"x")
    calls: list = []
    monkeypatch.setattr(dxf_file, "find_oda_converter", lambda: tmp_path / "oda.exe")
    dxf_file.open_file(str(source), runner=fake_converter(drawing, calls))
    assert calls[0][-1] == "heron-copy.dwg"


def test_an_empty_drawing_has_no_extents(tmp_path):
    ezdxf.new().saveas(tmp_path / "empty.dxf")
    assert read(tmp_path / "empty.dxf")["extents"] is None


def test_layers_carry_their_settings_and_object_counts(drawing):
    rows = {row["name"]: row for row in read(drawing, "layers")["rows"]}
    assert rows["M-DUCT"] == {"name": "M-DUCT", "color": 3, "linetype": "DASHED", "lineweight": -3, "on": True,
                              "frozen": False, "locked": False, "plottable": True, "objects": 4}  # fmt: skip
    assert rows["M-HIDDEN"]["plottable"] is False and rows["M-TEXT"]["objects"] == 2


def test_blocks_count_what_is_placed_and_what_sits_inside_other_blocks(drawing):
    rows = {row["name"]: row for row in read(drawing, "blocks")["rows"]}
    assert rows["VALVE"]["placed"] == 3 and rows["VALVE"]["inside_other_blocks"] == 1
    assert rows["VALVE"]["attributes"] == ["TAG"] and rows["PUMP-SKID"]["placed"] == 1
    assert rows["BASE"]["xref"] == "base-plan.dwg"
    only = read(drawing, "blocks", block_name="pump*")["rows"]
    assert [r["name"] for r in only] == ["PUMP-SKID"]


def test_text_and_mtext_in_model_and_layouts_with_filters(drawing):
    rows = read(drawing, "text")["rows"]
    assert {(r["text"], r["space"]) for r in rows} == {("FCU-03", "Model"), ("Supply AIR duct", "Model"), ("SHEET M-101", "Layout1")}
    assert [r["text"] for r in read(drawing, "text", contains="air")["rows"]] == ["Supply AIR duct"]
    assert {r["height"] for r in read(drawing, "text", layer="m-*")["rows"]} == {2.5, 3.5}


def test_attributes_as_rows_and_as_csv(drawing):
    rows = read(drawing, "attributes", block_name="VALVE")["rows"]
    assert [r["attributes"] for r in rows] == [{"TAG": "V-1"}, {"TAG": "V-2"}, {"TAG": "V-3"}]
    assert rows[1]["insertion"] == [100.0, 0.0, 0.0] and rows[0]["layer"] == "M-DUCT"
    csv_text = read(drawing, "attributes", output="csv")
    assert csv_text.splitlines()[0] == "block,handle,layer,x,y,z,TAG" and "V-3" in csv_text


def test_styles_list_text_styles_dimension_styles_and_linetypes(drawing):
    answer = read(drawing, "styles")
    assert "Standard" in [s["name"] for s in answer["text_styles"]]
    assert "Standard" in [s["name"] for s in answer["dim_styles"]]
    assert "DASHED" in [lt["name"] for lt in answer["linetypes"]]
    assert "layers" not in answer


def test_a_long_answer_is_cut_and_says_so(drawing):
    answer = read(drawing, "layers", max_items=2)
    assert len(answer["rows"]) == 2 and answer["count"] == 5 and "raise max_items" in answer["truncated"]


def test_the_file_is_never_changed(drawing):
    before = (drawing.read_bytes(), os.stat(drawing).st_mtime_ns)
    for what in ("summary", "layers", "blocks", "text", "attributes", "styles"):
        read(drawing, what)
    assert (drawing.read_bytes(), os.stat(drawing).st_mtime_ns) == before


def test_a_damaged_dxf_is_read_in_recover_mode_and_says_so(drawing, tmp_path):
    broken = tmp_path / "broken.dxf"
    broken.write_text(drawing.read_text().replace("  0\nEOF\n", ""))
    answer = read(broken, "layers")
    assert "M-DUCT" in [r["name"] for r in answer["rows"]] and "recover mode" in answer["recovered"]


@pytest.mark.parametrize(
    "make, words",
    [
        (lambda p: p / "nothing.dxf", "There is no file"),
        (lambda p: (p / "notes.txt").write_text("hi") and p / "notes.txt", ".dxf, .dwg, .dws and .dwt"),
        (lambda p: (p / "fake.dxf").write_text("not a drawing at all") and p / "fake.dxf", "Nothing was read"),
    ],
)
def test_a_wrong_file_is_refused_in_plain_words(tmp_path, make, words):
    with pytest.raises(AutocadError, match=words):
        read(make(tmp_path))


def test_a_relative_path_is_refused():
    with pytest.raises(AutocadError, match="full path"):
        read("drawings/M-101.dxf")


def test_a_file_too_big_is_refused(drawing, monkeypatch):
    monkeypatch.setattr(dxf_file, "MAX_MB", 0)
    with pytest.raises(AutocadError, match="Open it in AutoCAD instead"):
        read(drawing)


def test_without_ezdxf_it_says_how_to_install_it(drawing, monkeypatch):
    monkeypatch.setitem(sys.modules, "ezdxf", None)
    with pytest.raises(AutocadError, match="pip install ezdxf"):
        read(drawing)


# ---- DWG: the ODA File Converter, found never downloaded ---------------------


@pytest.fixture
def no_programs(tmp_path, monkeypatch):
    """No Program Files with ODA in them, nothing on PATH, no HERON_ODA_CONVERTER."""
    for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)", dxf_file.ODA_ENV):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Program Files"))
    monkeypatch.setattr(dxf_file.shutil, "which", lambda name: None)
    return tmp_path / "Program Files"


def test_a_dwg_without_the_converter_says_it_needs_autocad_or_oda(tmp_path, no_programs):
    dwg = tmp_path / "M-101.dwg"
    dwg.write_bytes(b"AC1032 not really")
    with pytest.raises(AutocadError) as caught:
        read(dwg)
    text = str(caught.value)
    assert "ODA File Converter" in text and "never downloads" in text and "open the drawing in AutoCAD" in text
    assert "save the drawing as DXF" in text and "Nothing was read" in text


def test_the_newest_converter_under_program_files_is_found(no_programs):
    for version in ("21.6.0", "25.12.0", "24.1.0"):
        exe = no_programs / "ODA" / f"ODAFileConverter {version}" / dxf_file.ODA_EXE
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")
    assert dxf_file.find_oda_converter().parent.name == "ODAFileConverter 25.12.0"


def test_heron_oda_converter_names_it_and_a_wrong_one_is_said(tmp_path, no_programs, monkeypatch):
    exe = tmp_path / "tools" / "ODAFileConverter.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    monkeypatch.setenv(dxf_file.ODA_ENV, str(exe))
    assert dxf_file.find_oda_converter() == exe
    monkeypatch.setenv(dxf_file.ODA_ENV, str(tmp_path / "gone.exe"))
    assert dxf_file.find_oda_converter() is None
    assert "HERON_ODA_CONVERTER names" in dxf_file.no_dwg_reader(Path("x.dwg"))


def fake_converter(made_from: Path, calls: list):
    """Stands in for ODAFileConverter: writes made_from's DXF where the converter would."""

    def runner(command, timeout):
        calls.append(command)
        _exe, inbox, outbox, version, kind, recurse, audit, name = command
        assert (version, kind, recurse, audit) == ("ACAD2018", "DXF", "0", "1")
        assert (Path(inbox) / name).is_file()  # the copy, never the source
        (Path(outbox) / (Path(name).stem + ".dxf")).write_bytes(made_from.read_bytes())
        return 0, "", ""

    return runner


@pytest.mark.parametrize("kind", [".dwg", ".dws", ".dwt"])
def test_a_dwg_is_converted_from_a_copy_and_read(drawing, tmp_path, monkeypatch, kind):
    source = tmp_path / f"office{kind}"
    source.write_bytes(b"pretend DWG bytes")
    exe = tmp_path / "ODAFileConverter.exe"
    calls: list = []
    monkeypatch.setattr(dxf_file, "find_oda_converter", lambda: exe)
    opened = dxf_file.open_file(str(source), runner=fake_converter(drawing, calls))
    assert "M-DUCT" in [layer.dxf.name for layer in opened.doc.layers]
    assert calls[0][0] == str(exe) and calls[0][-1] == "heron-copy.dwg"  # a plain name, as .dwg even for .dws / .dwt
    assert "ODA File Converter" in opened.read_by and source.read_bytes() == b"pretend DWG bytes"
    assert not Path(calls[0][1]).exists()  # the temporary folder is gone


def test_a_converter_that_makes_nothing_says_why(tmp_path, monkeypatch):
    source = tmp_path / "new.dwg"
    source.write_bytes(b"x")
    monkeypatch.setattr(dxf_file, "find_oda_converter", lambda: tmp_path / "oda.exe")
    with pytest.raises(AutocadError, match=r"made no DXF of new.dwg \(exit code 3, it said: unsupported version\)"):
        dxf_file.open_file(str(source), runner=lambda command, timeout: (3, "", "unsupported version\nmore"))


def test_the_converter_runs_with_no_input_and_a_time_limit():
    code, out, _err = dxf_file.run_program([sys.executable, "-c", "print('converted')"], 30)
    assert code == 0 and out.strip() == "converted"
    with pytest.raises(AutocadError, match="did not finish in 0 s and was stopped"):
        dxf_file.run_program([sys.executable, "-c", "import time; time.sleep(5)"], 0.3)
    with pytest.raises(AutocadError, match="could not be started"):
        dxf_file.run_program([str(Path(sys.executable).parent / "no-such-program")], 5)


# ---- the tool: Read, gated, and answering with AutoCAD closed ---------------


def test_it_is_a_read_tool_that_needs_no_autocad():
    assert risk_of("autocad_read_file") is Risk.READ
    assert "autocad_read_file" in gate.NO_AUTOCAD_TOOLS


def test_it_answers_with_the_bridge_on_and_no_autocad(drawing, monkeypatch):
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "on")
    gate.reset()
    answer = json.loads(asyncio.run(files.autocad_read_file(path=str(drawing), what="blocks")))
    assert answer["rows"][0]["name"] == "VALVE"
    refused = asyncio.run(files.autocad_read_file(path=str(drawing.with_suffix(".dwg"))))
    assert refused.startswith("Error:") and "There is no file" in refused


def test_why_does_not_ask_for_autocad_for_a_file_job(monkeypatch):
    from autocad_mcp.tools import resources

    entries = asyncio.run(resources._entries())
    answer = why.explain(
        "read the layers of a DXF file without AutoCAD",
        entries=entries,
        level_of=lambda tool: RISK.get(tool, Risk.ADMIN),
        descriptions={},
        known_tools=set(RISK),
        report={"plugin_installed": "1.5.0", "autocads_connected": [], "checks": []},
        bridge_on=True,
        chosen_pid=None,
        drawing_checked=False,
        no_autocad=gate.NO_AUTOCAD_TOOLS,
    )
    assert answer["tool"]["tool"] == "autocad_read_file"
    assert answer["can_run"] is True and "not_connected" not in [r["reason"] for r in answer["reasons"]]


# ---- the compare against a reference drawing (#69) --------------------------


def tables(**kinds):
    base = {"layers": [], "text_styles": [], "dim_styles": [], "linetypes": []}
    return {**base, **kinds}


LAYER = {"name": "M-DUCT", "color": 3, "linetype": "DASHED", "lineweight": 35, "plottable": True}
STYLE = {"name": "MEP-2.5", "font": "romans.shx", "bigfont": "", "family": "", "height": 2.5, "width": 0.8, "oblique": 0.0}


def rules(findings):
    return {(f["rule"], f["name"]) for f in findings}


def test_a_matching_drawing_has_no_findings():
    standard = tables(layers=[LAYER], text_styles=[STYLE], dim_styles=[{"name": "MEP-100"}], linetypes=[{"name": "DASHED"}])
    assert standard_compare.compare(standard, standard) == []


def test_missing_and_different_layers_are_named_with_both_values():
    here = tables(layers=[{**LAYER, "color": 1, "linetype": "Continuous", "lineweight": -3, "plottable": False}])
    found = standard_compare.compare(here, tables(layers=[LAYER, {**LAYER, "name": "M-PIPE"}]))
    assert rules(found) == {("layer_differs_from_standard", "M-DUCT"), ("standard_layer_missing", "M-PIPE")}
    detail = next(f["detail"] for f in found if f["name"] == "M-DUCT")
    assert "colour 1 here, 3 in the standard" in detail and "linetype Continuous here, DASHED" in detail
    assert "lineweight Default here, 0.35 mm in the standard" in detail and "does not plot here, plots" in detail


def test_names_only_this_drawing_has_are_listed_unless_left_out():
    here = tables(layers=[LAYER, {**LAYER, "name": "SKETCH"}, {**LAYER, "name": "0"}, {**LAYER, "name": "Defpoints"}],
                  linetypes=[{"name": "Continuous"}, {"name": "ByLayer"}, {"name": "ZIGZAG"}])  # fmt: skip
    found = standard_compare.compare(here, tables(layers=[LAYER]))
    assert rules(found) == {("layer_not_in_standard", "SKETCH"), ("linetype_not_in_standard", "ZIGZAG")}
    assert standard_compare.compare(here, tables(layers=[LAYER]), flag_extra=False) == []


def test_layers_and_styles_autocad_makes_itself_are_never_missing():
    standard = tables(layers=[{**LAYER, "name": "Defpoints"}], text_styles=[{**STYLE, "name": "Annotative"}])
    assert standard_compare.compare(tables(), standard) == []


def test_xref_and_anonymous_names_are_left_out_on_both_sides():
    here = tables(layers=[LAYER, {**LAYER, "name": "BASE|A-WALL"}], dim_styles=[{"name": "*D12"}])
    assert standard_compare.compare(here, tables(layers=[LAYER, {**LAYER, "name": "OLD|X"}])) == []


def test_names_match_without_case():
    assert standard_compare.compare(tables(layers=[{**LAYER, "name": "m-duct", "linetype": "dashed"}]), tables(layers=[LAYER])) == []


@pytest.mark.parametrize("font", ["romans", "ROMANS.SHX", "C:\\Program Files\\Autodesk\\Fonts\\romans.shx"])
def test_one_font_written_three_ways_is_the_same_font(font):
    assert standard_compare.compare(tables(text_styles=[{**STYLE, "font": font}]), tables(text_styles=[STYLE])) == []


def test_text_style_differences_are_named():
    here = tables(text_styles=[{**STYLE, "font": "arial.ttf", "height": 3.5, "width": 1.0, "oblique": 15.0}])
    found = standard_compare.compare(here, tables(text_styles=[STYLE]))
    detail = found[0]["detail"]
    assert found[0]["rule"] == "text_style_differs_from_standard"
    for words in ("font arial.ttf here, romans.shx", "height 3.5 here, 2.5", "width factor 1.0 here, 0.8", "oblique angle 15.0"):
        assert words in detail


def test_a_truetype_family_matches_its_file():
    here = tables(text_styles=[{**STYLE, "font": "", "family": "Arial"}])
    assert standard_compare.compare(here, tables(text_styles=[{**STYLE, "font": "arial.ttf"}])) == []


def test_dimension_styles_and_linetypes_are_compared_by_name():
    found = standard_compare.compare(tables(dim_styles=[{"name": "Standard"}]),
                                     tables(dim_styles=[{"name": "MEP-100"}], linetypes=[{"name": "HIDDEN2"}]))  # fmt: skip
    assert rules(found) == {("standard_dim_style_missing", "MEP-100"), ("standard_linetype_missing", "HIDDEN2")}
    assert "name only" in standard_compare.COMPARED["dim_styles"]


# ---- autocad_check_standards with a reference ------------------------------


class Item:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Collection:
    def __init__(self, items):
        self._items = items
        self.Count = len(items)

    def Item(self, i):
        return self._items[i]


class Style(Item):
    def GetFont(self):
        return (self.typeface, False, False, 0, 34)


def com_doc(full_name="C:\\Jobs\\M-101.dwg", layers=(("M-DUCT", 3, "DASHED"),), styles=(("Standard", "txt"),),
            dims=("Standard",), linetypes=("ByBlock", "ByLayer", "Continuous", "DASHED")):  # fmt: skip
    return Item(
        FullName=full_name,
        Layers=Collection([Item(Name=n, Color=c, Linetype=lt, Lineweight=-3, LayerOn=True, Freeze=False, Lock=False,
                                Plottable=True) for n, c, lt in layers]),  # fmt: skip
        TextStyles=Collection([Style(Name=n, FontFile=f, BigFontFile="", Height=0.0, Width=1.0, ObliqueAngle=0.0, typeface="")
                               for n, f in styles]),  # fmt: skip
        DimStyles=Collection([Item(Name=n) for n in dims]),
        Linetypes=Collection([Item(Name=n, Description="") for n in linetypes]),
    )


async def _direct(fn):
    return fn()


@pytest.fixture
def open_drawing(monkeypatch):
    doc = com_doc(layers=(("0", 7, "Continuous"), ("M-DUCT", 3, "DASHED"), ("M-TEXT", 2, "Continuous"), ("M-HIDDEN", 8, "Continuous")))
    monkeypatch.setattr(standards, "run", _direct)
    monkeypatch.setattr(standards, "get_doc", lambda: doc)
    return doc


def check(**kw):
    answer = asyncio.run(standards.autocad_check_standards(**kw))
    assert not answer.startswith("Error:"), answer
    return json.loads(answer)


def test_a_dxf_reference_is_read_by_heron_and_the_differences_found(drawing, open_drawing):
    report = check(reference=str(drawing))
    found = rules(report["findings"])
    assert ("layer_differs_from_standard", "M-TEXT") in found  # colour 2 here, 1 in the standard
    assert ("layer_differs_from_standard", "M-HIDDEN") in found  # plots here, not in the standard
    assert ("layer_differs_from_standard", "M-DUCT") not in found
    assert report["passed"] is False and report["source"] == f"the reference drawing {drawing}"
    assert report["reference"]["read_by"].startswith("ezdxf") and report["reference"]["compared"] == standard_compare.COMPARED
    assert report["checked"]["reference"]["layers"] == 5 and report["pass_means"] == PASS_MEANS
    assert "complies" not in json.dumps(report).replace("never means the drawing complies", "")


def test_a_reference_the_drawing_matches_passes_against_that_file(tmp_path, open_drawing):
    open_drawing.Layers = Collection([Item(Name="M-DUCT", Color=3, Linetype="DASHED", Lineweight=-3, LayerOn=True,
                                           Freeze=False, Lock=False, Plottable=True)])  # fmt: skip
    doc = ezdxf.new("R2018")
    doc.layers.add("M-DUCT", color=3, linetype="DASHED")
    doc.saveas(tmp_path / "std.dxf")
    report = check(reference=str(tmp_path / "std.dxf"), flag_extra=False)
    assert report["passed"] is True and report["findings"] == []


def test_a_dws_without_the_converter_is_read_by_autocad_objectdbx(drawing, open_drawing, monkeypatch, tmp_path):
    dws = tmp_path / "office.dws"
    dws.write_bytes(b"pretend")
    monkeypatch.setattr(standards.dxf_file, "find_oda_converter", lambda: None)
    opened = []

    class Dbx:
        def __init__(self):
            standard = com_doc(layers=(("M-DUCT", 5, "DASHED"),))
            self.Layers, self.TextStyles = standard.Layers, standard.TextStyles
            self.DimStyles, self.Linetypes = standard.DimStyles, standard.Linetypes

        def Open(self, path):
            opened.append(path)

    class App:
        Version = "25.1s (LMS Tech)"
        Documents = Collection([open_drawing])

        def GetInterfaceObject(self, progid):
            assert progid == "ObjectDBX.AxDbDocument.25"
            return Dbx()

    monkeypatch.setattr(standards, "get_app", lambda: App())
    report = check(reference=str(dws))
    assert opened == [str(dws)] and "ObjectDBX" in report["reference"]["read_by"]
    assert ("layer_differs_from_standard", "M-DUCT") in rules(report["findings"])


def test_a_reference_open_in_autocad_is_read_there(open_drawing, monkeypatch, tmp_path):
    ref = tmp_path / "office.dwg"
    ref.write_bytes(b"pretend")
    monkeypatch.setattr(standards.dxf_file, "find_oda_converter", lambda: None)
    other = com_doc(full_name=str(ref), layers=(("M-DUCT", 3, "DASHED"),))

    class App:
        Documents = Collection([open_drawing, other])

        def GetInterfaceObject(self, progid):  # pragma: no cover - must not be needed
            raise AssertionError("the open drawing is read where it is")

    monkeypatch.setattr(standards, "get_app", lambda: App())
    report = check(reference=str(ref))
    assert report["reference"]["read_by"].startswith("AutoCAD: the drawing is open there")


def test_a_failing_converter_hands_the_dwg_to_autocad(drawing, open_drawing, monkeypatch, tmp_path):
    ref = tmp_path / "office.dwg"
    ref.write_bytes(b"pretend")
    monkeypatch.setattr(standards.dxf_file, "find_oda_converter", lambda: tmp_path / "oda.exe")
    monkeypatch.setattr(standards.dxf_file, "run_program", lambda command, timeout: (1, "", "crashed"))
    standard = com_doc(layers=(("M-DUCT", 3, "DASHED"),))

    class App:
        Version = "24.3"
        Documents = Collection([open_drawing])

        def GetInterfaceObject(self, progid):
            standard.Open = lambda path: None
            return standard

    monkeypatch.setattr(standards, "get_app", lambda: App())
    report = check(reference=str(ref))
    assert "ODA File Converter could not read it" in report["reference"]["note"] and "ObjectDBX" in report["reference"]["read_by"]


def test_a_damaged_reference_is_never_a_pass(open_drawing, tmp_path):
    # Found in review: a reference cut short loses its layers, and "nothing differs" must not be a PASS.
    open_drawing.Layers = Collection([])
    doc = ezdxf.new("R2018")
    doc.layers.add("M-DUCT", color=3)
    doc.saveas(tmp_path / "std.dxf")
    broken = tmp_path / "broken.dxf"
    broken.write_text((tmp_path / "std.dxf").read_text().replace("  0\nEOF\n", ""))
    report = check(reference=str(broken), flag_extra=False)
    assert report["findings"] and report["passed"] is False  # M-DUCT is still missing here
    open_drawing.Layers = Collection([Item(Name="M-DUCT", Color=3, Linetype="Continuous", Lineweight=-3, LayerOn=True,
                                           Freeze=False, Lock=False, Plottable=True)])  # fmt: skip
    report = check(reference=str(broken), flag_extra=False)
    assert report["passed"] is None and "recover mode" in report["reference"]["warning"]


def test_a_reference_with_nothing_to_compare_is_not_decided(open_drawing, tmp_path):
    ezdxf.new("R2018").saveas(tmp_path / "empty.dxf")
    report = check(reference=str(tmp_path / "empty.dxf"), flag_extra=False)
    assert report["passed"] is None and "holds no layers, styles or linetypes" in report["reference"]["warning"]


def test_a_reference_table_autocad_cannot_read_stops_the_check(open_drawing, monkeypatch, tmp_path):
    ref = tmp_path / "office.dws"
    ref.write_bytes(b"pretend")
    monkeypatch.setattr(standards.dxf_file, "find_oda_converter", lambda: None)

    class Broken:
        @property
        def Count(self):
            raise OSError("the table is damaged")

    class Dbx:
        Layers, TextStyles, DimStyles, Linetypes = Broken(), Collection([]), Collection([]), Collection([])

        def Open(self, path):
            pass

    class App:
        Version = "25.0"
        Documents = Collection([open_drawing])

        def GetInterfaceObject(self, progid):
            return Dbx()

    monkeypatch.setattr(standards, "get_app", lambda: App())
    answer = asyncio.run(standards.autocad_check_standards(reference=str(ref)))
    assert answer.startswith("Error:") and "could not read the layers" in answer and "Nothing was checked" in answer


def test_rules_and_a_reference_together_name_both_sources(drawing, open_drawing):
    report = check(rules={"layer_name_pattern": "^M-"}, reference=str(drawing))
    assert report["source"] == f"the rules given in this chat and the reference drawing {drawing}"
    assert "layer_name" not in report["summary"]  # 0 is never held to the pattern
    assert report["summary"]["layer_differs_from_standard"] >= 1


@pytest.mark.parametrize(
    "reference, words",
    [("C:\\nowhere\\office.dws", "full path|There is no reference drawing"), ("office.dws", "full path")],
)
def test_a_reference_that_is_not_there_is_refused(open_drawing, reference, words):
    answer = asyncio.run(standards.autocad_check_standards(reference=reference))
    assert answer.startswith("Error:") and any(w in answer for w in words.split("|"))


def test_a_reference_of_the_wrong_kind_is_refused(open_drawing, tmp_path):
    (tmp_path / "rules.json").write_text("{}")
    answer = asyncio.run(standards.autocad_check_standards(reference=str(tmp_path / "rules.json")))
    assert answer.startswith("Error:") and ".dws, .dwg, .dwt or .dxf" in answer


def test_neither_rules_nor_a_reference_says_both_ways(open_drawing):
    answer = asyncio.run(standards.autocad_check_standards())
    assert answer.startswith("Error:") and "'reference'" in answer and "'rules'" in answer


def test_the_new_parts_need_the_same_padlock_as_before():
    assert risk_of("autocad_check_standards") is Risk.READ

