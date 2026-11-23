"""Live checks for sheets made by the plug-in (group AF).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Only what the tools' answers and ``autocad_list_layouts`` can show is measured:
which tab is on screen, how many tabs there are, and the words of a refusal. Page
Setup, the title block copied by CopyLayout, the PDFs and Ctrl+Z are looked at by a
person; so are the rows that need a plug-in older than this change, a second
drawing with an xref, or a printer's paper list.
"""

from __future__ import annotations

from live_common import Check, Context, expect, parse, refusal

from autocad_mcp.tools import drawing_tools, sheets


async def _tabs() -> tuple[list[str], str]:
    out = parse(await drawing_tools.autocad_list_layouts())
    return [str(row["name"]) for row in out["layouts"]], str(out["active"])


async def af2_five_sheets_made_without_switching_tab(ctx: Context) -> str:
    before, on_screen = await _tabs()
    names = [f"LC-AF2-{n}" for n in range(102, 107)]
    made_by = set()
    for name in names:
        made = parse(await sheets.autocad_create_layout(name=name, paper_size="A1", activate=False))
        expect(made.get("created") is True and made.get("layout") == name, f"{name}: the answer is {str(made)[:140]}")
        expect(not made.get("warning"), f"{name} came with a warning (busy?): {str(made.get('warning'))[:140]}")
        expect(not made.get("activated"), f"{name} says it was switched to although activate=false")
        made_by.add(str(made.get("made_by")))
    after, still = await _tabs()
    expect(len(after) == len(before) + 5 and all(n in after for n in names), f"the tabs went from {before} to {after}, not five more")
    expect(still == on_screen, f"the tab on screen changed from {on_screen} to {still}")
    return (f"five tabs {names[0]} to {names[-1]} made one after another (made_by {', '.join(sorted(made_by))}), each answer "
            f"created with no warning, none switched to; the tab on screen stayed {on_screen}")


async def af4_a_bad_paper_plotter_or_style_leaves_no_tab(ctx: Context) -> str:
    before, _ = await _tabs()
    said = []
    for name, kwargs in (("LC-AF4-A7", {"paper_size": "A7"}), ("LC-AF4-PLOTTER", {"plotter": "No Such.pc3"}),
                         ("LC-AF4-STYLE", {"plot_style_table": "none.ctb"})):
        words = refusal(await sheets.autocad_create_layout(name=name, **kwargs))
        expect(words.strip(), f"{name}: the refusal says nothing")
        said.append(f"{next(iter(kwargs.values()))}: {words[:110]}")
    after, _ = await _tabs()
    expect(after == before, f"the refusals left tabs behind: {[n for n in after if n not in before]}")
    return ("each of the three was refused and no tab was left (" + " | ".join(said)
            + "). Whether the words name what the plotter does offer is for you to read here")


CHECKS: tuple[Check, ...] = (
    Check("AF2", "AF", "five sheets made without switching tab", af2_five_sheets_made_without_switching_tab),
    Check("AF4", "AF", "a bad paper, plotter or style leaves no tab", af4_a_bad_paper_plotter_or_style_leaves_no_tab),
)

_OLD_PLUGIN = "needs a Heron plug-in older than this change installed instead of the current one"

BY_EYE: dict[str, str] = {
    "AF1": "Page Setup shows the plotter, paper and style, the tab is seen on screen, and one Ctrl+Z is pressed by hand",
    "AF3": "needs a sheet with a title block and a viewport to copy, and the copy looked at",
    "AF5": "Properties, the viewport's content and the status bar's annotation scale are read on screen",
    "AF6": "which way the plan reads on the sheet decides the sign of the twist, and that is looked at",
    "AF7": "the plan shown only inside the L, and Properties, are looked at, and one Ctrl+Z each",
    "AF8": "needs SCALELISTEDIT and annotative text seen at its height on the paper",
    "AF9": "needs one Ctrl+Z pressed by hand and, again, Discard answered with Ask to Keep on",
    "AF10": "needs a layout tab made active by hand first, and the table seen on the sheet",
    "AF11": _OLD_PLUGIN,
    "AF12": "needs a folder of three saved drawings and the PDF's pages looked at",
    "AF13": "needs a drawing opened and changed by hand, and a folder to publish",
    "AF14": "needs an xref file renamed in Windows and then unloaded by hand",
    "AF15": "needs two saved drawings and the PDF's page order looked at",
    "AF16": "needs AutoCAD 2025 / 2026 and 2021-2024 machines, which are not here",
    "AF17": "needs a drawing from acad.dwt in inches and a template sheet that plots turned 90 degrees",
    "AF18": "needs a nested xref and its file renamed in Windows",
    "AF19": _OLD_PLUGIN + ", then the current one, and the add-in log read",
    "AF20": "reads Page Setup on the SAC2 sheets and how the white paper looks on screen",
    "AF21": "the paper seen on screen has to agree with the answer, and that is looked at",
    "AF22": "the preview picture and the PDF are looked at to see which sheet they show",
    "AF23": "a tab switch by LISP, then an erase that brings up Heron's erase question",
    "AF24": "the block's members are compared in the small preview against AutoCAD's own display",
}
