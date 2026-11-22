"""The tests test this checkout's own code, never an installed copy from another folder (#35).

A worktree shares the main checkout's .venv, whose editable install points at the main
checkout's src/. Without `pythonpath = ["src"]` in pyproject.toml a test run in the worktree
imported the main checkout's server and said nothing about the worktree's code.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import script_env

ROOT = Path(__file__).resolve().parents[1]
OWN = ROOT / "src" / "autocad_mcp"


def test_the_server_package_is_this_checkouts_own():
    import autocad_mcp

    found = Path(autocad_mcp.__file__).resolve().parent
    assert found == OWN.resolve(), f"the tests imported autocad_mcp from {found}, not from this checkout ({OWN})"


def test_a_script_a_test_starts_imports_this_checkouts_own_too():
    done = subprocess.run(
        [sys.executable, "-c", "import autocad_mcp; print(autocad_mcp.__file__)"],
        capture_output=True, text=True, timeout=60, env=script_env(), cwd=str(ROOT.parent),
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    assert Path(done.stdout.strip()).resolve().parent == OWN.resolve()


def test_this_checkouts_src_comes_before_any_other_copy(tmp_path):
    # Another checkout's server first on PYTHONPATH, as a stale editable install would be.
    other = tmp_path / "other" / "src" / "autocad_mcp"
    other.mkdir(parents=True)
    (other / "__init__.py").write_text("__version__ = 'other checkout'\n", encoding="utf-8")
    env = script_env()
    env["PYTHONPATH"] = str(other.parent)
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(ROOT),
         "-c", str(ROOT / "pyproject.toml"), str(Path(__file__).resolve()) + "::test_the_server_package_is_this_checkouts_own"],
        capture_output=True, text=True, timeout=120, env=env, cwd=str(ROOT),
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
