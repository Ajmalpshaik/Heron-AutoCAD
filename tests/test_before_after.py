"""Before / after values for every changed object (D-62), and no undo step when nothing differs.

COM is faked: each fake records whether an undo group was opened, so a job
that would change nothing is shown to leave no (empty) undo step.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.tools import (
    _shared,
    document,
    layers,
    modify,
    settings,
    takeoff,
    text_tools,
)


class Doc:
    def __init__(self) -> None:
        self.groups = 0
        self.vars: dict[str, object] = {"DIMSCALE": 50.0, "OSMODE": 0}
        self.Layers = LayerTable()
        self.ActiveLayer = self.Layers.Item("0")

    def StartUndoMark(self):
        self.groups += 1

    def EndUndoMark(self):
        pass

    def GetVariable(self, name):
        return self.vars[name]

    def SetVariable(self, name, value):
        self.vars[name] = value


class Layer:
    def __init__(self, name: str) -> None:
        self.Name = name
        self.Color, self.Linetype, self.Lineweight = 7, "Continuous", -3
        self.LayerOn, self.Freeze, self.Lock, self.Plottable = True, False, False, True


class LayerTable:
    def __init__(self) -> None:
        self.layers = {"0": Layer("0"), "M-DUCT": Layer("M-DUCT"), "M-PIPE": Layer("M-PIPE")}

    @property
    def Count(self):
        return len(self.layers)

    def Item(self, key):
        if isinstance(key, int):
            return list(self.layers.values())[key]
        for name, layer in self.layers.items():
            if name.casefold() == str(key).casefold():
                return layer
        raise KeyError(key)

    def Add(self, name):
        self.layers[name] = Layer(name)
        return self.layers[name]


class Line:
    ObjectName = "AcDbLine"

    def __init__(self, handle: str, layer: str = "0", color: int = 256) -> None:
        self.Handle, self.Layer, self.Color, self.Linetype = handle, layer, color, "ByLayer"

    def Update(self):
        pass


@pytest.fixture
def doc(monkeypatch):
    fake = Doc()

    async def now(fn):
        return fn()

    for module in (modify, layers, document, settings, takeoff, text_tools):
        monkeypatch.setattr(module, "run", now, raising=False)
        monkeypatch.setattr(module, "get_doc", lambda: fake, raising=False)
        monkeypatch.setattr(module, "require_idle", lambda d: None, raising=False)
    return fake


def answer(coro) -> dict:
    return json.loads(asyncio.run(coro))


# --- the shared list ------------------------------------------------------------


def test_the_list_is_short_with_a_count_of_the_rest():
    rows = [{"handle": str(i), "property": "layer", "from": "0", "to": "A"} for i in range(120)]
    listed = _shared.before_after(rows)
    assert len(listed["before_after"]) == 50 and listed["before_after_more"] == 70
    assert _shared.before_after(rows[:3]) == {"before_after": rows[:3]}


def test_values_read_the_way_a_draftsman_says_them():
    listed = _shared.before_after([{"variable": "LIMMAX", "from": (0.1000000001, 2.0), "to": 3.0}])
    assert listed["before_after"][0]["from"] == [0.1, 2.0]
    assert _shared.same_value("a-wall", "A-WALL") and not _shared.same_value(1, 2.0)
    assert not _shared.same_value(True, 0) and _shared.same_value(50, 50.0)


# --- autocad_modify_entity ---------------------------------------------------------


def test_modify_entity_lists_old_and_new_per_object(doc, monkeypatch):
    lines = {"2A": Line("2A", "0", 256), "2B": Line("2B", "M-DUCT", 1)}
    monkeypatch.setattr(modify, "resolve_handle", lambda d, h: lines[h])
    monkeypatch.setattr(modify, "short_type", lambda e: "line")
    result = answer(modify.autocad_modify_entity(handles=["2A", "2B"], layer="M-DUCT", color="red"))
    assert result["before_after"] == [
        {"handle": "2A", "property": "layer", "from": "0", "to": "M-DUCT"},
        {"handle": "2A", "property": "color", "from": 256, "to": 1},
    ]
    assert result["already"] == ["2B"] and result["handles"] == ["2A"]
    assert lines["2A"].Layer == "M-DUCT" and lines["2A"].Color == 1
    assert doc.groups == 1


def test_modify_entity_that_changes_nothing_opens_no_undo_step(doc, monkeypatch):
    monkeypatch.setattr(modify, "resolve_handle", lambda d, h: Line(h, "M-DUCT"))
    monkeypatch.setattr(modify, "short_type", lambda e: "line")
    result = answer(modify.autocad_modify_entity(handles=["2A"], layer="m-duct"))
    assert result["modified"] == 0 and result["before_after"] == []
    assert doc.groups == 0


def test_a_property_a_line_does_not_have_is_skipped_not_listed(doc, monkeypatch):
    monkeypatch.setattr(modify, "resolve_handle", lambda d, h: Line(h))
    monkeypatch.setattr(modify, "short_type", lambda e: "line")
    result = answer(modify.autocad_modify_entity(handles=["2A"], radius=5))
    assert result["skipped"] == [{"handle": "2A", "type": "line", "property": "radius"}]
    assert result["before_after"] == [] and doc.groups == 0


# --- layers and variables ------------------------------------------------------------


def test_set_layer_state_lists_each_layer_and_skips_the_ones_already_so(doc):
    doc.Layers.Item("M-PIPE").LayerOn = False
    result = answer(layers.autocad_set_layer_state(name="M-*", on=False))
    assert result["before_after"] == [{"layer": "M-DUCT", "property": "on", "from": True, "to": False}]
    assert result["changed"] == ["M-DUCT"] and result["already"] == 1
    assert doc.groups == 1
    again = answer(layers.autocad_set_layer_state(name="M-*", on=False))
    assert again["before_after"] == [] and doc.groups == 1  # no second, empty undo step


def test_set_current_layer_lists_the_switch_and_nothing_when_already_current(doc):
    result = answer(layers.autocad_set_current_layer(name="M-DUCT"))
    assert {"variable": "CLAYER", "property": "current layer", "from": "0", "to": "M-DUCT"} in result["before_after"]
    groups = doc.groups
    again = answer(layers.autocad_set_current_layer(name="m-duct"))
    assert again["before_after"] == [] and doc.groups == groups


def test_create_layer_lists_what_it_changed_on_an_existing_layer(doc, monkeypatch):
    monkeypatch.setattr(layers, "describe_layer", lambda layer: {"name": layer.Name, "color": layer.Color})
    result = answer(layers.autocad_create_layer(name="M-DUCT", color="cyan"))
    assert result["before_after"] == [{"layer": "M-DUCT", "property": "color", "from": 7, "to": 4}]
    groups = doc.groups
    again = answer(layers.autocad_create_layer(name="M-DUCT", color="cyan"))
    assert again["before_after"] == [] and again["created"] is False and doc.groups == groups


def test_set_variable_lists_the_old_and_new_value(doc):
    result = answer(document.autocad_set_variable(name="dimscale", value="100"))
    assert result["before_after"] == [{"variable": "DIMSCALE", "property": "value", "from": 50.0, "to": 100.0}]
    again = answer(document.autocad_set_variable(name="DIMSCALE", value="100"))
    assert again["before_after"] == []


# --- attributes, find and replace, dynamic blocks ---------------------------------------


def test_set_attributes_lists_old_and_new(doc, monkeypatch):
    class Att:
        def __init__(self, tag, text):
            self.TagString, self.TextString = tag, text

    class Ref:
        def __init__(self):
            self.atts = [Att("REV", "A")]

        def GetAttributes(self):
            return self.atts

        def Update(self):
            pass

    ref = Ref()
    refs = [{"handle": "5C", "block": "TB", "layout": "E-101", "attributes": {"REV": "A"}}]
    monkeypatch.setattr(text_tools, "_attribute_refs", lambda d, b, layer: (refs, {"5C": ref}))
    result = answer(text_tools.autocad_set_attributes(values={"REV": "B"}))
    assert result["before_after"] == [{"handle": "5C", "property": "attribute REV", "from": "A", "to": "B"}]
    assert ref.atts[0].TextString == "B"
    refs[0]["attributes"]["REV"] = "B"
    groups = doc.groups
    assert answer(text_tools.autocad_set_attributes(values={"REV": "B"}))["before_after"] == []
    assert doc.groups == groups


def test_set_dynamic_properties_lists_old_and_new_and_skips_equal_values(doc, monkeypatch):
    class Prop:
        def __init__(self, name, value, allowed=()):
            self.PropertyName, self.Value, self.AllowedValues = name, value, allowed
            self.ReadOnly, self.Description = False, ""

    class Ref:
        Handle, Name, EffectiveName = "7A", "*U2", "DOOR"
        props = [Prop("Width", 800.0), Prop("Visibility1", "LEFT", ("LEFT", "RIGHT"))]

        def GetDynamicBlockProperties(self):
            return self.props

        IsDynamicBlock = True

    monkeypatch.setattr(takeoff, "resolve_handle", lambda d, h: Ref())
    monkeypatch.setattr(takeoff, "_dynamic_properties", lambda ref: Ref.props)
    result = answer(takeoff.autocad_set_dynamic_properties(handle="7A", values={"Width": 900, "visibility1": "LEFT"}))
    assert result["before_after"] == [{"handle": "7A", "property": "Width", "from": 800.0, "to": 900.0}]
    assert result["already"] == ["Visibility1"]
    assert doc.groups == 1


def test_drawing_setup_with_nothing_to_change_opens_no_undo_step(doc):
    result = answer(settings.autocad_drawing_setup(dimscale=50))
    assert result["unchanged"] == ["DIMSCALE"] and result["before_after"] == []
    assert doc.groups == 0
    changed = answer(settings.autocad_drawing_setup(dimscale=100))
    assert changed["before_after"] == [{"variable": "DIMSCALE", "property": "value", "from": 50.0, "to": 100.0}]
    assert doc.groups == 1
