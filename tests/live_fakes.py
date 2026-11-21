"""Play recorded AutoCAD answers into a live check, without AutoCAD.

A live check (tools/live_check*.py) calls Heron's tools as ``module.autocad_x(...)``
and the runner's own AutoCAD helpers as ``lc.name(...)``. ``play`` puts a recorded
answer in the place of each one the check is expected to call, runs the check, and
says what it judged:

    verdict = play(monkeypatch, check, {
        "autocad_draw_line": {"created": True, "handle": "1A"},       # every call
        "autocad_get_entity": [first_answer, second_answer],          # one per call, in order
        "autocad_get_variable": lambda name: {"value": VALUES[name]}, # worked out from the arguments
        "lc.read_props": {"Lineweight": 35},                          # a runner helper
    })
    assert verdict.passed, verdict.evidence

The fake checks every call the way the real tool would take it: the argument names
must be the tool's own (the real signature is bound), so a check that passes a
misspelt argument fails here, not in front of AutoCAD. A call to anything not in the
recording fails the test too, so the recording lists everything the check does.

A dict answer is sent as JSON; a str is sent as it is, so a refusal is recorded
as "Error: ...", and a change job's plain first line as "DONE - ...\\n\\n{...}".
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import pkgutil
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import live_common as lc  # noqa: E402

import autocad_mcp.tools as tool_package  # noqa: E402


def load(name: str) -> Any:
    """A module from tools/ (live_common, live_check_edits ...), which is not a package."""
    return importlib.import_module(name)


def tool_modules() -> dict[str, Any]:
    """Every Heron tool function by name -> the module that holds it."""
    found: dict[str, Any] = {}
    for info in pkgutil.iter_modules(tool_package.__path__):
        module = importlib.import_module(f"autocad_mcp.tools.{info.name}")
        for name, value in vars(module).items():
            if name.startswith("autocad_") and callable(value) and getattr(value, "__module__", "") == module.__name__:
                found[name] = module
    return found


TOOL_HOMES = tool_modules()


@dataclass
class Verdict:
    passed: bool
    refused: bool
    evidence: str
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def called(self, name: str) -> list[dict[str, Any]]:
        return [kwargs for tool, kwargs in self.calls if tool == name]


def _as_reply(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


@dataclass
class Sequence:
    """Answers given one per call, in order (a plain list is one answer: a JSON array)."""

    items: list[Any]


def seq(*items: Any) -> Sequence:
    return Sequence(list(items))


class _Recording:
    def __init__(self, answers: dict[str, Any]):
        # A copy, so one recording can be played more than once.
        self.answers = {k: Sequence(list(v.items)) if isinstance(v, Sequence) else v for k, v in answers.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def next(self, name: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append((name, kwargs))
        recorded = self.answers[name]
        if isinstance(recorded, Sequence):
            if not recorded.items:
                raise AssertionError(f"{name} was called more often than the recording has answers for")
            recorded = recorded.items.pop(0)
        if callable(recorded):
            recorded = recorded(**kwargs)
        return recorded


def _fake_tool(recording: _Recording, name: str, real: Callable) -> Callable:
    signature = inspect.signature(real)

    async def fake(*args: Any, **kwargs: Any) -> Any:
        if args:
            raise AssertionError(f"call {name} by keyword, as a chat does: {args}")
        try:
            signature.bind(**kwargs)
        except TypeError as exc:
            raise AssertionError(f"{name} would not take these arguments: {kwargs} ({exc})") from exc
        return _as_reply(recording.next(name, kwargs))

    return fake


def _fake_helper(recording: _Recording, name: str, real: Callable) -> Callable:
    signature = inspect.signature(real)
    is_async = inspect.iscoroutinefunction(real)

    def call(*args: Any, **kwargs: Any) -> Any:
        try:
            bound = signature.bind(*args, **kwargs)
        except TypeError as exc:
            raise AssertionError(f"lc.{name} would not take these arguments ({exc})") from exc
        given = {k: v for k, v in bound.arguments.items() if k != "ctx"}
        return recording.next(f"lc.{name}", given)

    if is_async:
        async def fake(*args: Any, **kwargs: Any) -> Any:
            return call(*args, **kwargs)

        return fake
    return call


def play(monkeypatch: Any, check: Any, answers: dict[str, Any], ctx: lc.Context | None = None) -> Verdict:
    """Run one check against recorded answers. Every tool or helper it calls must be in the recording."""
    recording = _Recording(answers)
    for name, module in TOOL_HOMES.items():
        if name in answers:
            monkeypatch.setattr(module, name, _fake_tool(recording, name, getattr(module, name)))
        else:
            monkeypatch.setattr(module, name, _unexpected(name))
    for name in HELPERS:
        real = getattr(lc, name)
        if f"lc.{name}" in answers:
            monkeypatch.setattr(lc, name, _fake_helper(recording, name, real))
        else:
            monkeypatch.setattr(lc, name, _unexpected(f"lc.{name}", asynchronous=inspect.iscoroutinefunction(real)))
    unknown = [k for k in answers if k not in TOOL_HOMES and k.removeprefix("lc.") not in HELPERS]
    if unknown:
        raise AssertionError(f"the recording names things that do not exist: {unknown}")
    context = ctx or lc.Context(version="27.0", padlocks={"changes": True, "admin": True, "publish": True})
    context.scratch = context.scratch or "Drawing1.dwg"
    run = check.run if hasattr(check, "run") else check
    try:
        evidence = asyncio.run(run(context))
        return Verdict(True, False, str(evidence), recording.calls)
    except lc.Refused as exc:
        return Verdict(False, True, str(exc), recording.calls)
    except lc.Failed as exc:
        return Verdict(False, False, str(exc), recording.calls)


# The runner's own AutoCAD helpers a check may call (live_common.py).
HELPERS = (
    "read_padlocks", "save_scratch", "other_drawing", "activate", "drawing_names", "read_props",
    "exists", "by_hand_line", "by_hand_group", "by_hand_width", "by_hand_true_colour", "file_stamp",
)


def _unexpected(name: str, asynchronous: bool = True) -> Callable:
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"the check called {name}, which the recording does not cover")

    if not asynchronous:
        return fail

    async def afail(*args: Any, **kwargs: Any) -> Any:
        fail()

    return afail
