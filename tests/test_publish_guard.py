"""A raw command or AutoLISP may not save, plot or export (D-47).

Admin lets autocad_send_command and autocad_run_lisp through, and those can
type QSAVE or -PLOT themselves: a save over a shared file with the Publish
padlock off. The server refuses the ones it can see; the plug-in vetoes the
same list inside a job (PublishGuard.cs). The two lists must stay the same.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from autocad_mcp.tools import advanced
from autocad_mcp.tools.advanced import (
    PUBLISH_COMMANDS,
    publish_call_in_lisp,
    publish_command_in,
)

ROOT = Path(__file__).resolve().parents[1]
GUARD_CS = ROOT / "autocad" / "Heron.AutoCAD.Bridge" / "PublishGuard.cs"


def test_the_server_and_the_plug_in_stop_the_same_commands():
    text = GUARD_CS.read_text(encoding="utf-8")
    block = text[text.index("Commands = new HashSet") : text.index("};", text.index("Commands = new HashSet"))]
    in_plugin = set(re.findall(r'"([A-Z0-9]+)"', block))
    assert in_plugin == set(PUBLISH_COMMANDS)


@pytest.mark.parametrize(
    "command",
    ["_QSAVE\n", "QSAVE", "_.SAVEAS\n2018\nC:/x.dwg\n", "-PLOT\nY\n", "_-EXPORT\n", "_LINE\n0,0\n1,1\n\n_QSAVE\n", "etransmit"],
)
def test_a_save_plot_or_export_in_a_command_is_found(command):
    assert publish_command_in(command)


@pytest.mark.parametrize("command", ["_LINE\n0,0\n100,0\n\n", "-LAYER\nM\nM-PIPE\n\n", "_FILLET\n_R\n50\n", "SAVETIME"])
def test_ordinary_commands_are_not(command):
    assert publish_command_in(command) is None


@pytest.mark.parametrize(
    "expression",
    [
        '(command "_.QSAVE")',
        '(vl-cmdf "_-PLOT" "Y")',
        "(vla-save (vla-get-activedocument (vlax-get-acad-object)))",
        '(vla-SaveAs doc "C:/x.dwg")',
        '(command "_-EXPORT" "PDF")',
    ],
)
def test_a_save_plot_or_export_in_lisp_is_found(expression):
    assert publish_call_in_lisp(expression)


@pytest.mark.parametrize(
    "expression",
    ['(getvar "DIMSCALE")', '(command "_.LINE" "0,0" "1,1" "")', '(setq name "save the date")', "(vla-get-saved doc)"],
)
def test_ordinary_lisp_is_not(expression):
    assert publish_call_in_lisp(expression) is None


def test_send_command_refuses_before_anything_is_sent():
    result = asyncio.run(advanced.autocad_send_command(command="_QSAVE\n"))
    assert result.startswith("Error: QSAVE saves, plots or exports")
    assert "autocad_save_drawing" in result and "Nothing was sent" in result


def test_run_lisp_refuses_before_anything_is_sent():
    result = asyncio.run(advanced.autocad_run_lisp(expression='(command "_.QSAVE")'))
    assert result.startswith("Error: QSAVE saves, plots or exports")
