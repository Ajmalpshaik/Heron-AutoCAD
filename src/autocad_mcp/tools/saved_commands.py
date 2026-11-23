"""Saved commands: a job proven in the chat, kept with named inputs and replayed exactly (D-55).

The idea is Heron AI for Revit's saved commands (its docs/49): the modeller
works a job out once with the chat, then keeps it under a name, with the
values that change each time as inputs ({{size}}, {{layer}}). Running it
again fills the inputs and runs the very same steps, through the same gate,
padlocks and Keep or Discard as autocad_sequence: the chat does not plan it
again, so it comes out the same every time. It is AutoCAD's Action Recorder
habit, with the safety of Heron.

A saved command is a sequence, so it holds the Changes padlock only: no
save, export, command or AutoLISP step can be saved. The commands are files
on this PC, never written into a drawing.
"""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from ..core import gate
from ..core.errors import AutocadError
from ..core.folders import heron_local
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from . import sequence

MAX_COMMANDS = 100
PLACEHOLDER = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
WHOLE = re.compile(r"^\{\{\s*([a-z][a-z0-9_]*)\s*\}\}$")


def commands_dir() -> Path:
    return heron_local() / "commands"


def _file(name: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise AutocadError("Give the command a name, e.g. 'pipe support' or 'A1 sheet set-up'.")
    return commands_dir() / f"{slug}.json"


def placeholders(node: Any) -> set[str]:
    """Every {{input}} named anywhere in the steps."""
    if isinstance(node, str):
        return set(PLACEHOLDER.findall(node))
    if isinstance(node, dict):
        return set().union(*(placeholders(value) for value in node.values())) if node else set()
    if isinstance(node, list):
        return set().union(*(placeholders(value) for value in node)) if node else set()
    return set()


def fill(node: Any, values: dict[str, Any]) -> Any:
    """The steps with every {{input}} replaced. A value that is a whole {{input}} keeps its type."""
    if isinstance(node, str):
        whole = WHOLE.match(node)
        if whole:
            return copy.deepcopy(values[whole.group(1)])
        return PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), node)
    if isinstance(node, dict):
        return {key: fill(value, values) for key, value in node.items()}
    if isinstance(node, list):
        return [fill(value, values) for value in node]
    return node


def _values(record: dict[str, Any], given: dict[str, Any]) -> dict[str, Any]:
    inputs = record.get("inputs", {})
    unknown = sorted(set(given) - set(inputs))
    if unknown:
        raise AutocadError(f"'{record['name']}' has no input called {', '.join(unknown)}. Its inputs: {', '.join(inputs) or 'none'}.")
    values = {}
    for name, spec in inputs.items():
        if name in given:
            values[name] = given[name]
        elif "default" in spec:
            values[name] = spec["default"]
        else:
            raise AutocadError(f"'{record['name']}' needs '{name}': {spec.get('description', 'no description')}.")
    return values


def check(name: str, steps: list[dict[str, Any]], inputs: dict[str, Any]) -> dict[str, Any]:
    """The command made whole, or AutocadError naming what is wrong. Runs nothing."""
    if not steps:
        raise AutocadError("A saved command needs at least one step.")
    for number, step in enumerate(steps, 1):
        if isinstance(step, dict) and str(step.get("tool", "")).removeprefix("autocad_") == "saved_command":
            raise AutocadError(f"Step {number} runs a saved command; a saved command cannot run another. Put its steps here.")
    spec: dict[str, dict[str, Any]] = {}
    for key, value in (inputs or {}).items():
        if not re.match(r"^[a-z][a-z0-9_]*$", key):
            raise AutocadError(f"'{key}' cannot be an input name: use lower-case words joined by _, e.g. pipe_size.")
        if not isinstance(value, dict):
            value = {"description": str(value)}
        if "example" not in value and "default" not in value:
            raise AutocadError(f"Input '{key}' needs an 'example' (or a 'default'), so the steps can be checked now.")
        spec[key] = {k: value[k] for k in ("description", "default", "example") if k in value}
    named = placeholders(steps)
    missing = sorted(named - set(spec))
    if missing:
        raise AutocadError(f"The steps use {', '.join('{{' + m + '}}' for m in missing)}, which are not declared as inputs.")
    unused = sorted(set(spec) - named)
    if unused:
        raise AutocadError(f"The inputs {', '.join(unused)} are not used in any step.")
    sample = {key: value.get("example", value.get("default")) for key, value in spec.items()}
    sequence.plan_steps(fill(steps, sample))  # the same checks a sequence makes: tool, level, arguments
    return {"name": name.strip(), "inputs": spec, "steps": steps}


def saved() -> list[dict[str, Any]]:
    found = []
    folder = commands_dir()
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            try:
                found.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    return found


def load(name: str) -> dict[str, Any]:
    try:
        return json.loads(_file(name).read_text(encoding="utf-8"))
    except OSError:
        names = [record["name"] for record in saved()]
        raise AutocadError(
            f"There is no saved command called '{name}'." + (f" There are: {', '.join(names)}." if names else "")
        ) from None


def steps_of(args: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The steps a 'run' will run, inputs filled, for the gate: a replace step makes it a replace job (D-140)."""
    name = args.get("name")
    if args.get("action") != "run" or args.get("dry_run") or not name:
        return []
    record = load(name)
    filled = fill(record["steps"], _values(record, args.get("inputs") or {}))
    return sequence.steps_of({"steps": filled})


gate.STEPS_OF["autocad_saved_command"] = steps_of


@mcp.tool(name="autocad_saved_command", **tool_meta("Saved Commands"))
@tool_errors
async def autocad_saved_command(
    action: Annotated[
        Literal["list", "show", "save", "run", "delete"],
        Field(description="'list' the saved commands, 'show' one, 'save' one, 'run' one, or 'delete' one."),
    ] = "list",
    name: Annotated[str | None, Field(description="The command's name, e.g. 'pipe support' or 'A1 sheet set-up'.")] = None,
    steps: Annotated[
        list[dict[str, Any]] | None,
        Field(description=(
            "For save: the steps exactly as autocad_sequence takes them, with {{input}} where a value "
            "changes each time, e.g. {\"tool\": \"autocad_add_solid\", \"args\": {\"kind\": \"box\", "
            "\"length\": \"{{length}}\"}}."
        )),
    ] = None,
    inputs: Annotated[
        dict[str, Any] | None,
        Field(description=(
            "For save: each input as {description, example} or {description, default}. For run: the "
            "values, e.g. {\"length\": 1200}."
        )),
    ] = None,
    description: Annotated[str | None, Field(description="For save: what the command does, in the modeller's words.")] = None,
    dry_run: Annotated[bool, Field(description="For run: fill the inputs and check every step, run none.")] = False,
) -> str:
    """Save a job that worked as a named command with inputs, and run it again the same way.

    Once a job is right ("a pipe support at this size"), save its steps with
    the values that change as {{inputs}}. Running it fills the inputs and runs
    the same steps through the gate, padlocks and Keep or Discard, exactly as
    autocad_sequence would: nothing is planned again, so it comes out the same
    each time. Saved on this PC, never in the drawing. Like a sequence, it
    holds the Changes padlock only.

    Args:
        action (str): list, show, save, run or delete.
        name (str): the command.
        steps (list[dict]): for save.
        inputs (dict): for save, the inputs' descriptions and examples; for run, the values.
        description (str): for save.
        dry_run (bool): for run.

    Returns:
        str: JSON. run: the sequence's own report, plus "command" and "inputs".

    Examples:
        - Use when: "save that as 'pipe support' so I can do it again with another size".
        - Use when: "do the pipe support again, 150 diameter" -> run with inputs.
        - Use when: "what commands have we saved?" -> list.
        - Don't use when: the job is new - work it out with the tools first, then save it.
        - Don't use when: a step saves, exports or runs a command - those are refused,
          call them on their own.

    Error Handling:
        - A step a sequence would refuse, an input used but not declared (or declared
          but not used), or an input without an example is refused when saving;
          nothing is saved.
        - Running with an unknown or missing input names it; nothing is run.
    """
    if action == "list":
        listed = [{"name": r["name"], "description": r.get("description", ""), "inputs": sorted(r.get("inputs", {})),
                   "steps": len(r.get("steps", []))} for r in saved()]  # fmt: skip
        return dumps({"commands": listed})
    if not name:
        raise AutocadError(f"'{action}' needs the command's name.")
    if action == "show":
        return dumps(load(name))
    if action == "delete":
        path = _file(name)
        if not path.is_file():
            raise AutocadError(f"There is no saved command called '{name}'.")
        path.unlink()
        return dumps({"deleted": name})
    if action == "save":
        record = check(name, steps or [], inputs or {})
        record["description"] = (description or "").strip()
        path = _file(name)
        if not path.is_file() and len(saved()) >= MAX_COMMANDS:
            raise AutocadError(f"There are already {MAX_COMMANDS} saved commands. Delete one first.")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(record, indent=2), encoding="utf-8")
        os.replace(temp, path)
        return dumps({"saved": record["name"], "inputs": sorted(record["inputs"]), "steps": len(record["steps"])})

    record = load(name)
    values = _values(record, inputs or {})
    filled = fill(record["steps"], values)
    body = getattr(sequence.autocad_sequence, "__wrapped__", sequence.autocad_sequence)
    report = json.loads(await body(steps=filled, stop_on_error=True, dry_run=dry_run))
    return dumps({"command": record["name"], "inputs": values, **report})
