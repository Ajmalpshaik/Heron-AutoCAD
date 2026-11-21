"""tools/check_structure.py: the repository rules CI enforces."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_structure", ROOT / "tools" / "check_structure.py")
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)


def test_autocad_api_outside_the_addin_is_caught(tmp_path):
    (tmp_path / "autocad" / "Heron.AutoCAD.Addin").mkdir(parents=True)
    (tmp_path / "autocad" / "Heron.AutoCAD.Bridge").mkdir(parents=True)
    (tmp_path / "autocad" / "Heron.AutoCAD.Addin" / "Ok.cs").write_text("using Autodesk.AutoCAD.Runtime;")
    (tmp_path / "autocad" / "Heron.AutoCAD.Bridge" / "Bad.cs").write_text("using Autodesk.AutoCAD.Runtime;")
    problems = cs.autocad_api_outside_addin(tmp_path)
    assert len(problems) == 1 and "Bad.cs" in problems[0]


def test_broken_doc_link_is_caught(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("[ok](b.md) [web](https://x.y) [gone](missing.md) [anchor](#top)")
    (tmp_path / "docs" / "b.md").write_text("b")
    problems = cs.broken_links(tmp_path)
    assert len(problems) == 1 and "missing.md" in problems[0]


def test_session_worktrees_under_dot_claude_are_not_checked(tmp_path):
    # The main checkout holds other sessions' worktrees in .claude/worktrees: their
    # add-in copies are not "AutoCAD API outside the add-in" (seen 2026-11-21).
    copy = tmp_path / ".claude" / "worktrees" / "some-session" / "autocad" / "Heron.AutoCAD.Addin"
    copy.mkdir(parents=True)
    (copy / "HeronRibbon.cs").write_text("using Autodesk.Windows;")
    (copy.parents[1] / "README.md").write_text("[gone](missing.md)")
    assert cs.autocad_api_outside_addin(tmp_path) == []
    assert cs.broken_links(tmp_path) == []


def test_this_repository_passes():
    assert cs.run_all(ROOT) == []
