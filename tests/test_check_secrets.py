"""tools/check_secrets.py: no credential reaches this public repository.

The look-alike keys are built at run time, so this file never holds one.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("check_secrets", ROOT / "tools" / "check_secrets.py")
check_secrets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_secrets)

FAKE = {
    "Anthropic API key": "sk-" + "ant-" + "a1B2" * 10,
    "GitHub token": "gh" + "p_" + "Z9y8" * 10,
    "AWS access key": "AKIA" + "ABCDEFGH12345678",
    "private key": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "password or token in a config line": 'password = "' + "hunter2hunter2" + '"',
}


@pytest.mark.parametrize("what", sorted(FAKE))
def test_each_shape_is_found(what):
    found = check_secrets.scan_text("first line\n" + FAKE[what] + "\n")
    assert (2, what) in found


def test_an_allowed_line_is_skipped():
    assert check_secrets.scan_text(FAKE["GitHub token"] + "  # " + check_secrets.ALLOW) == []


@pytest.mark.parametrize(
    "line",
    ['password = os.environ["HERON_PASSWORD"]', "token = None", 'api_key: "${{ secrets.KEY }}"', "sk-ant- is the prefix"],
)
def test_ordinary_code_is_not_a_finding(line):
    assert check_secrets.scan_text(line) == []


def test_files_named_like_credentials_are_found(tmp_path):
    for name in (".env", "deploy.pem", "id_rsa", "app.env.example"):
        (tmp_path / name).write_text("x\n", encoding="utf-8")
    problems = check_secrets.scan(tmp_path, [".env", "deploy.pem", "id_rsa", "app.env.example"])
    assert len(problems) == 3
    assert not any("example" in problem for problem in problems)


def test_the_value_itself_is_never_printed(tmp_path):
    (tmp_path / "config.json").write_text(FAKE["Anthropic API key"] + "\n", encoding="utf-8")
    problems = check_secrets.scan(tmp_path, ["config.json"])
    assert problems == ["config.json:1: looks like a Anthropic API key"]
    assert FAKE["Anthropic API key"] not in problems[0]


def test_binary_files_are_skipped(tmp_path):
    (tmp_path / "icon.png").write_bytes(b"\x89PNG\0\0" + FAKE["AWS access key"].encode())
    assert check_secrets.scan(tmp_path, ["icon.png"]) == []


def test_this_repository_is_clean():
    assert check_secrets.scan(ROOT) == []
