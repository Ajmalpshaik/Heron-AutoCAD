"""autocad_create_styles: multileader and table styles made by the plug-in (#68, D-104, D-105).

The values are the plug-in's to check (Heron.AutoCAD.Bridge/StylePlans.cs, with
its own tests); here: what is sent, in which order, what is refused before
anything is written, and how one style's failure is reported.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from autocad_mcp.core.bridge import BridgeRefused
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import _shared, settings

STYLE_PLANS = Path(__file__).resolve().parents[1] / "autocad" / "Heron.AutoCAD.Bridge" / "StylePlans.cs"


class FakeTextStyle:
    def __init__(self, name):
        self.Name = name
        self.fontFile = ""
        self.Height = 0.0
        self.Width = 1.0
        self.ObliqueAngle = 0.0


class FakeTextStyles:
    def __init__(self):
        self.items = [FakeTextStyle("Standard")]

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index]

    def Add(self, name):
        style = FakeTextStyle(name)
        self.items.append(style)
        return style


class FakeDrawing:
    def __init__(self, log):
        self.log = log
        self.TextStyles = FakeTextStyles()

    def StartUndoMark(self):
        self.log.append("undo begin")

    def EndUndoMark(self):
        self.log.append("undo end")


class FakePlugin:
    """Answers each operation in turn: a dict is what it made, an exception is raised."""

    def __init__(self, log):
        self.log = log
        self.calls: list[tuple[str, dict]] = []
        self.answers: list[object] = []

    def __call__(self, operation, args):
        self.calls.append((operation, args))
        self.log.append(operation)
        answer = self.answers.pop(0) if self.answers else {"name": args["name"], "created": True}
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def log():
    return []


@pytest.fixture
def drawing(monkeypatch, log):
    doc = FakeDrawing(log)

    async def run(fn):
        return fn()

    monkeypatch.setattr(settings, "run", run)
    monkeypatch.setattr(settings, "get_doc", lambda: doc)
    monkeypatch.setattr(settings, "require_idle", lambda d: None)
    return doc


@pytest.fixture
def plugin(monkeypatch, log):
    fake = FakePlugin(log)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: fake)
    return fake


def call(**kwargs) -> dict:
    answer = asyncio.run(settings.autocad_create_styles(**kwargs))
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


def error(**kwargs) -> str:
    answer = asyncio.run(settings.autocad_create_styles(**kwargs))
    assert answer.startswith("Error"), answer
    return answer


class TestWhatIsSent:
    def test_a_multileader_style_goes_to_the_plug_in_with_replace(self, drawing, plugin):
        out = call(multileader_styles=[{"name": " MEP-LABEL-50 ", "text_height": 2.5, "scale": "1:50"}])
        assert plugin.calls == [
            ("multileader_style", {"name": "MEP-LABEL-50", "text_height": 2.5, "scale": "1:50", "replace": False})
        ]
        assert out["multileader_styles"] == [{"name": "MEP-LABEL-50", "created": True}]
        assert "table_styles" not in out

    def test_a_table_style_goes_to_the_plug_in(self, drawing, plugin):
        out = call(table_styles=[{"name": "SCHEDULE", "text_height": 2.5, "alignment": "left"}], replace=True)
        assert plugin.calls == [
            ("table_style", {"name": "SCHEDULE", "text_height": 2.5, "alignment": "left", "replace": True})
        ]
        assert out["table_styles"][0]["created"] is True
        assert "multileader_styles" not in out

    def test_text_styles_come_first_so_a_style_can_use_one_made_with_it(self, drawing, plugin, log):
        out = call(
            text_styles=[{"name": "ROMANS", "font": "romans.shx"}],
            multileader_styles=[{"name": "TAG", "text_style": "ROMANS", "text_height": 2.5}],
            table_styles=[{"name": "SCHEDULE", "text_style": "ROMANS", "text_height": 2.5}],
        )
        assert out["text_styles"][0]["created"] is True
        assert [row["name"] for row in out["multileader_styles"] + out["table_styles"]] == ["TAG", "SCHEDULE"]
        # One undo mark round all of it.
        assert log == ["undo begin", "multileader_style", "table_style", "undo end"]
        assert [s.Name for s in drawing.TextStyles.items] == ["Standard", "ROMANS"]


class TestRefusedBeforeAnythingIsWritten:
    def test_a_misspelt_option(self, drawing, plugin, log):
        message = error(
            text_styles=[{"name": "ROMANS"}],
            multileader_styles=[{"name": "TAG", "text_height": 2.5, "arow": "dot"}],
        )
        assert "arow is not an option" in message and "arrow" in message and "Nothing was changed" in message
        assert plugin.calls == [] and log == []
        assert len(drawing.TextStyles.items) == 1

    def test_replace_inside_a_style_points_at_the_call(self, drawing, plugin):
        assert "replace is given once" in error(table_styles=[{"name": "A", "text_height": 2.5, "replace": True}])
        assert plugin.calls == []

    @pytest.mark.parametrize("name", ["", "  ", "MEP/50", None])
    def test_a_name_autocad_would_not_take(self, drawing, plugin, name):
        error(multileader_styles=[{"name": name, "text_height": 2.5}])
        assert plugin.calls == []

    def test_a_style_that_is_not_an_object(self, drawing, plugin):
        assert "is an object" in error(table_styles=["SCHEDULE"])

    def test_without_the_plug_in(self, drawing, monkeypatch, log):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        message = error(text_styles=[{"name": "ROMANS"}], table_styles=[{"name": "A", "text_height": 2.5}])
        assert "--no-bridge" in message and "Nothing was changed" in message
        assert log == [] and len(drawing.TextStyles.items) == 1

    def test_nothing_asked_for(self, drawing, plugin):
        assert "multileader_styles" in error()


class TestOneStyleFailing:
    def test_autocad_refusing_one_style_is_that_styles_row(self, drawing, plugin):
        plugin.answers = [
            AutocadError("This drawing has no text style called 'ROMANS'. Nothing was changed."),
            {"name": "B", "created": True},
        ]
        out = call(multileader_styles=[{"name": "A", "text_height": 2.5, "text_style": "ROMANS"},
                                       {"name": "B", "text_height": 2.5}])
        first, second = out["multileader_styles"]
        assert first == {"name": "A", "created": False,
                         "notes": ["This drawing has no text style called 'ROMANS'. Nothing was changed."]}
        assert second["created"] is True
        assert len(plugin.calls) == 2

    def test_an_unknown_outcome_stops_the_rest_once_something_was_made(self, drawing, plugin):
        plugin.answers = [{"name": "A", "created": True}, AutocadError("Outcome unknown: no answer.")]
        out = call(multileader_styles=[{"name": "A", "text_height": 2.5}, {"name": "B", "text_height": 2.5}],
                   table_styles=[{"name": "C", "text_height": 2.5}])
        assert [row["created"] for row in out["multileader_styles"]] == [True, False]
        assert out["multileader_styles"][1]["notes"] == ["Outcome unknown: no answer."]
        assert out["table_styles"] == [{"name": "C", "created": False, "notes": ["Not tried: Outcome unknown: no answer."]}]
        assert len(plugin.calls) == 2

    def test_the_plug_in_refusing_after_a_text_style_is_reported_not_raised(self, drawing, plugin):
        plugin.answers = [BridgeRefused("The modeller pressed HERONSTOP. Nothing was sent to AutoCAD.")]
        out = call(text_styles=[{"name": "ROMANS"}], table_styles=[{"name": "A", "text_height": 2.5}])
        assert out["text_styles"][0]["created"] is True
        assert "HERONSTOP" in out["table_styles"][0]["notes"][0]

    def test_the_plug_in_refusing_with_nothing_made_is_an_error(self, drawing, plugin):
        plugin.answers = [BridgeRefused("Heron in AutoCAD does not have the operation 'table_style'. Nothing was sent to AutoCAD.")]
        assert "does not have the operation" in error(table_styles=[{"name": "A", "text_height": 2.5}])

    def test_a_refused_text_style_is_not_counted_as_made(self):
        assert not settings._made_anything({"text_styles": [{"name": "A", "created": False, "notes": ["already"]}]})
        assert settings._made_anything({"text_styles": [{"name": "A", "created": False, "font": "romans.shx"}]})
        assert settings._made_anything({"dim_styles": [{"name": "A", "created": True}]})


def _bridge_options(plan_class: str) -> set[str]:
    """The option names one plan's From() reads in StylePlans.cs."""
    source = STYLE_PLANS.read_text(encoding="utf-8")
    body = source[source.index(f"public sealed class {plan_class}"):]
    following = body.find("public sealed class", 1)
    body = body if following < 0 else body[:following]
    found = set(re.findall(r'args\.(?:Text|Flag|Element)\("(\w+)"', body))
    found |= set(re.findall(r'(?:Size|Gap)\(args, "(\w+)"', body))
    return found


@pytest.mark.parametrize(
    ("plan_class", "options"),
    [("MultileaderStylePlan", settings.MULTILEADER_OPTIONS), ("TableStylePlan", settings.TABLE_OPTIONS)],
)
def test_the_options_are_the_ones_the_plug_in_reads(plan_class, options):
    # replace comes from the call, not from each style.
    assert _bridge_options(plan_class) == set(options) | {"replace"}


def test_no_plot_style_table_option():
    # D-105: AutoCAD's .NET API cannot write a .ctb / .stb, so there is no option that pretends to.
    assert "plot_style_tables" not in settings.autocad_create_styles.__wrapped__.__code__.co_varnames
