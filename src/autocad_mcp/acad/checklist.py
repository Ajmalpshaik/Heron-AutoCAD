"""Named check lists: the modeller's own sentences, run as checks (D-52).

The idea is Heron AI for Revit's QA checklists (its docs/50): each line the
modeller writes ("nothing on layer 0", "every title block filled in") becomes
a check from a fixed catalogue, run against the drawing, with PASS, FAIL,
NO DATA or NOT RUN, how many objects fail, which ones (so autocad_show can
put them on screen), and the severity, clause and advice the modeller gave it.

Four results (D-64):
  PASS     the checked value is met, for what Heron read, against the source
           named on the line. Never a statement that the drawing complies.
  FAIL     the checked value is not met; the objects are named.
  NO DATA  could not decide: what the check needs is not in the drawing or
           could not be read (no such title block, xrefs unreadable, only part
           of the objects read). Never counted as a PASS.
  NOT RUN  switched off by the project's changes.
Every run ends with a coverage line: "2 of 4 decided, 1 no data, 1 not run".

Office and project (D-64): a check list is the office's. A project may lay
changes on top, but only to a check's severity, its target (the values the
check compares against) and whether it is on. It may not add a check, change
what a check does, or rename one: no hidden logic in a project.

Everything here is pure: it judges data the tool gathered over COM, so every
rule is tested without AutoCAD.
"""

from __future__ import annotations

import re
from typing import Any

PASS, FAIL, NO_DATA, NOT_RUN = "PASS", "FAIL", "NO DATA", "NOT RUN"
STATES = (FAIL, NO_DATA, NOT_RUN, PASS)
OFFICE, PROJECT = "office", "project"
PROJECT_MAY_CHANGE = ("severity", "target", "on")
PASS_MEANS = (
    "PASS means the checked value is met, for what Heron read in this drawing, against the "
    "source named on the line. It is not a sign-off: Heron never says a drawing meets a code "
    "or standard. A person checks the drawing and signs it."
)
SEVERITIES = ("high", "medium", "low")
MOST_HANDLES = 100
BYLAYER_COLOR = 256

# Each check: what it means in words, and the parameters it takes.
CATALOGUE: dict[str, dict[str, Any]] = {
    "nothing_on_layer_0": {"means": "No drawn object sits on layer 0.", "params": {}},
    "nothing_on_defpoints": {"means": "No drawn object sits on Defpoints (it never plots).", "params": {}},
    "bylayer_colour": {"means": "Every object's colour is ByLayer.", "params": {}},
    "bylayer_linetype": {"means": "Every object's linetype is ByLayer.", "params": {}},
    "no_overlapping_dimensions": {"means": "No two dimensions lie on top of each other.", "params": {}},
    "layer_names": {
        "means": "Every layer name (except 0 and Defpoints) matches the office pattern.",
        "params": {"pattern": "a regular expression, e.g. '^(M|E|P|A)-'"},
    },
    "xrefs_found": {"means": "Every xref points at a file that is there.", "params": {}},
    "title_block_filled": {
        "means": "Every title block has every attribute filled in.",
        "params": {"block": "the title block's name, or a pattern such as 'TITLE*' or 'A1*'"},
    },
    "text_heights": {
        "means": "Every text and MText height is one of the office heights.",
        "params": {"heights": "the allowed heights in drawing units, e.g. [2.5, 3.5, 5]"},
    },
}

STARTER = {
    "name": "before issue",
    "checks": [
        {"check": "nothing_on_layer_0", "label": "Nothing on layer 0", "severity": "medium",
         "advice": "Move it to its discipline layer (autocad_remap_layers or autocad_tidy_entities)."},
        {"check": "nothing_on_defpoints", "label": "Nothing on Defpoints", "severity": "high",
         "advice": "Defpoints never plots: move it to a layer that does."},
        {"check": "bylayer_colour", "label": "Colours ByLayer", "severity": "low",
         "advice": "Set the colour back to ByLayer, so the layer decides how it plots."},
        {"check": "xrefs_found", "label": "Every xref found", "severity": "high",
         "advice": "Re-path the broken xref before issuing (autocad_manage_xref)."},
        {"check": "no_overlapping_dimensions", "label": "No dimensions on top of each other", "severity": "medium",
         "advice": "Delete the copy or move it to its own place."},
    ],
}  # fmt: skip


def validate(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each check made whole, or ValueError naming the line that is wrong."""
    if not checks:
        raise ValueError("A check list needs at least one check.")
    clean = []
    ids: set[str] = set()
    for number, given in enumerate(checks, 1):
        if not isinstance(given, dict):
            raise ValueError(f"Check {number} must be an object with a 'check'.")
        key = str(given.get("check", "")).strip()
        if key not in CATALOGUE:
            raise ValueError(f"Check {number}: '{key}' is not a check Heron has. It has: {', '.join(CATALOGUE)}.")
        params = dict(given.get("params") or {})
        for needed in CATALOGUE[key]["params"]:
            if needed not in params:
                raise ValueError(f"Check {number} ('{key}') needs '{needed}': {CATALOGUE[key]['params'][needed]}.")
        _check_params(f"Check {number}", key, params)
        severity = _severity(f"Check {number}", given.get("severity", "medium"))
        ident = _ident(given.get("id") or key)
        if not ident:
            raise ValueError(f"Check {number}: the id must have letters or digits, e.g. 'title_blocks'.")
        base, extra = ident, 2
        while ident in ids:
            if given.get("id"):
                raise ValueError(f"Check {number}: the id '{ident}' is used twice; each check needs its own.")
            ident, extra = f"{base}_{extra}", extra + 1
        ids.add(ident)
        clean.append({
            "id": ident,
            "check": key,
            "label": str(given.get("label") or CATALOGUE[key]["means"]),
            "params": params,
            "severity": severity,
            "clause": str(given.get("clause", "")),
            "advice": str(given.get("advice", "")),
        })  # fmt: skip
    return clean


def _ident(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")


def _severity(where: str, value: Any) -> str:
    severity = str(value).lower()
    if severity not in SEVERITIES:
        raise ValueError(f"{where}: severity must be one of {', '.join(SEVERITIES)}.")
    return severity


def _check_params(where: str, key: str, params: dict[str, Any]) -> None:
    """Refuse a parameter that cannot be used, naming the line."""
    if key == "layer_names":
        try:
            re.compile(str(params["pattern"]))
        except re.error as exc:
            raise ValueError(f"{where}: the pattern does not read as a regular expression ({exc}).") from None
    if key == "text_heights":
        heights = params["heights"]
        if not isinstance(heights, list) or not heights or not all(
            isinstance(h, (int, float)) and not isinstance(h, bool) and h > 0 for h in heights
        ):
            raise ValueError(f"{where}: 'heights' must be a list of positive numbers.")


def validate_changes(office: list[dict[str, Any]], changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A project's changes made whole, or ValueError naming the line that is wrong.

    A change names an office check by its id and may set only its severity,
    its target (the same parameters the office check has, new values) and
    whether it is on. Anything else is refused: a project never adds a check
    or changes what one does.
    """
    by_id = {check["id"]: check for check in office}
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for number, given in enumerate(changes, 1):
        where = f"Project change {number}"
        if not isinstance(given, dict):
            raise ValueError(f"{where} must be an object with an 'id'.")
        ident = _ident(given.get("id", ""))
        if ident not in by_id:
            raise ValueError(
                f"{where}: the office list has no check '{given.get('id', '')}', and a project cannot add one. "
                f"It has: {', '.join(by_id)}. Add a new check to the office list instead."
            )
        if ident in seen:
            raise ValueError(f"{where}: '{ident}' is changed twice; put both changes in one line.")
        seen.add(ident)
        other = sorted(set(given) - {"id", *PROJECT_MAY_CHANGE})
        if other:
            raise ValueError(
                f"{where} ('{ident}'): a project may only change {', '.join(PROJECT_MAY_CHANGE)}; "
                f"not {', '.join(other)}. What a check does belongs in the office list."
            )
        change: dict[str, Any] = {"id": ident}
        if "severity" in given:
            change["severity"] = _severity(where, given["severity"])
        if "on" in given:
            if not isinstance(given["on"], bool):
                raise ValueError(f"{where} ('{ident}'): 'on' must be true or false.")
            change["on"] = given["on"]
        if "target" in given:
            key = by_id[ident]["check"]
            allowed = CATALOGUE[key]["params"]
            target = given["target"]
            if not allowed:
                raise ValueError(f"{where} ('{ident}'): {key} has no target to change.")
            if not isinstance(target, dict) or not target:
                raise ValueError(f"{where} ('{ident}'): 'target' must be an object, e.g. {{{next(iter(allowed))!r}: ...}}.")
            unknown = sorted(set(target) - set(allowed))
            if unknown:
                raise ValueError(f"{where} ('{ident}'): {key} takes only {', '.join(allowed)} as its target; not {', '.join(unknown)}.")
            _check_params(where, key, {**by_id[ident]["params"], **target})
            change["target"] = dict(target)
        if len(change) == 1:
            raise ValueError(f"{where} ('{ident}'): say what changes: {', '.join(PROJECT_MAY_CHANGE)}.")
        clean.append(change)
    return clean


def layer(office: list[dict[str, Any]], changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The checks a run uses: the office list with the project's changes on top.

    Each check says where it came from ("office" or "project") and, when the
    project changed it, what it changed from what. The order and the checks
    are the office's: a project can switch one off, never add one.
    """
    by_id = {change["id"]: change for change in changes}
    used = []
    for check in office:
        row = {**check, "params": dict(check["params"]), "on": True, "from": OFFICE}
        change = by_id.get(check["id"])
        if change:
            changed: dict[str, Any] = {}
            if "severity" in change and change["severity"] != check["severity"]:
                changed["severity"] = {"office": check["severity"], "project": change["severity"]}
                row["severity"] = change["severity"]
            if "target" in change:
                new = {**check["params"], **change["target"]}
                if new != check["params"]:
                    changed["target"] = {"office": check["params"], "project": new}
                    row["params"] = new
            if change.get("on") is False:
                changed["on"] = {"office": True, "project": False}
                row["on"] = False
            if changed:
                row["from"] = PROJECT
                row["project_changed"] = changed
        used.append(row)
    return used


def needs(checks: list[dict[str, Any]]) -> set[str]:
    """What the tool must read from the drawing for these checks."""
    wanted = {"layers"}
    for check in checks:
        if check.get("on") is False:
            continue
        key = check["check"]
        if key == "xrefs_found":
            wanted.add("xrefs")
        elif key == "title_block_filled":
            wanted.add("blocks")
        elif key not in ("layer_names",):
            wanted.add("entities")
    return wanted


def block_pattern(text: str) -> re.Pattern[str]:
    """'TITLE*' or 'A1?' as AutoCAD wildcards, matched whole and without case."""
    return re.compile("^" + re.escape(text).replace(r"\*", ".*").replace(r"\?", ".") + "$", re.IGNORECASE)


def _overlapping(entities: list[dict[str, Any]]) -> list[str]:
    boxes = [(e["handle"], e["box"]) for e in entities if "Dimension" in str(e.get("type")) and e.get("box")]
    found: list[str] = []
    for i, (_handle, box) in enumerate(boxes):
        for other, theirs in boxes[i + 1 :]:
            if all(abs(a - b) < 1e-6 for a, b in zip(box, theirs, strict=True)):
                found.append(other)
    return list(dict.fromkeys(found))


def _failing(check: dict[str, Any], data: dict[str, Any]) -> tuple[str, list[str], str]:
    """(state, failing handles or names, a note)."""
    key, params = check["check"], check["params"]
    entities = data.get("entities")
    if key == "layer_names":
        regex = re.compile(str(params["pattern"]))
        bad = [str(layer["name"]) for layer in data.get("layers", [])
               if str(layer["name"]).lower() not in ("0", "defpoints") and not regex.search(str(layer["name"]))]  # fmt: skip
        return (FAIL if bad else PASS), bad, "layer names"
    if key == "xrefs_found":
        broken = data.get("xrefs_broken")
        if broken is None:
            return NO_DATA, [], "the xrefs could not be read"
        return (FAIL if broken else PASS), list(broken), "xref names"
    if key == "title_block_filled":
        pattern = block_pattern(str(params["block"]))
        blocks = [b for b in data.get("blocks", []) if pattern.match(str(b.get("name", "")))]
        if not blocks:
            return NO_DATA, [], f"no block named {params['block']} is in the drawing"
        bad = [b["handle"] for b in blocks if not b.get("attributes") or any(not str(v).strip() for v in b["attributes"].values())]
        return (FAIL if bad else PASS), bad, f"{len(blocks)} title block(s) read"
    if entities is None:
        return NO_DATA, [], "the objects could not be read"
    if key == "nothing_on_layer_0":
        bad = [e["handle"] for e in entities if str(e.get("layer")) == "0"]
    elif key == "nothing_on_defpoints":
        bad = [e["handle"] for e in entities if str(e.get("layer")).lower() == "defpoints" and e.get("type") != "AcDbViewport"]
    elif key == "bylayer_colour":
        bad = [e["handle"] for e in entities if e.get("color") not in (BYLAYER_COLOR, None)]
    elif key == "bylayer_linetype":
        bad = [e["handle"] for e in entities if str(e.get("linetype", "bylayer")).lower() != "bylayer"]
    elif key == "no_overlapping_dimensions":
        bad = _overlapping(entities)
    elif key == "text_heights":
        allowed = [float(h) for h in params["heights"]]
        texts = [e for e in entities if e.get("height") is not None]
        if not texts and not data.get("capped"):
            return NO_DATA, [], "no text with a height was read, so there was nothing to compare"
        bad = [e["handle"] for e in texts
               if not any(abs(float(e["height"]) - h) <= 1e-3 * max(h, 1) for h in allowed)]  # fmt: skip
    else:  # pragma: no cover - validate() refuses anything else
        return NO_DATA, [], "unknown check"
    if data.get("capped") and not bad:
        # Nothing wrong in the part read is not a PASS for the whole drawing.
        return NO_DATA, [], f"only the first {data['capped']} objects were read; the rest were not checked"
    return (FAIL if bad else PASS), bad, f"{len(entities)} object(s) read"


def coverage(counts: dict[str, int]) -> str:
    """'2 of 4 decided, 1 no data, 1 not run': decided is PASS plus FAIL."""
    total = sum(counts.get(state, 0) for state in STATES)
    decided = counts.get(PASS, 0) + counts.get(FAIL, 0)
    return f"{decided} of {total} decided, {counts.get(NO_DATA, 0)} no data, {counts.get(NOT_RUN, 0)} not run"


def _source(check: dict[str, Any], name: str) -> str:
    """What the checked value is measured against: the modeller's clause, else the list itself."""
    if check.get("clause"):
        return str(check["clause"])
    if check.get("from") == PROJECT:
        return f"check list '{name}', as changed for this project"
    return f"office check list '{name}'"


def verdict_of(counts: dict[str, int]) -> str:
    """FAIL if anything failed; NO DATA if anything could not be decided; PASS only when every check that was on passed."""
    if counts.get(FAIL):
        return FAIL
    if counts.get(NO_DATA):
        return NO_DATA
    if counts.get(PASS):
        return PASS
    return NOT_RUN


def run(name: str, checks: list[dict[str, Any]], data: dict[str, Any]) -> dict[str, Any]:
    """Every check's result, worst first, a verdict and the coverage line."""
    results = []
    for check in checks:
        if check.get("on") is False:
            state, bad, note = NOT_RUN, [], "switched off for this project"
        else:
            state, bad, note = _failing(check, data)
        row = {
            "id": check.get("id", check["check"]),
            "check": check["check"],
            "label": check["label"],
            "state": state,
            "severity": check["severity"],
            "failing": len(bad),
            "note": note,
            "source": _source(check, name),
            "from": check.get("from", OFFICE),
        }
        if check["params"]:
            row["target"] = check["params"]
        if check.get("project_changed"):
            row["project_changed"] = check["project_changed"]
        if bad:
            row["handles" if check["check"] not in ("layer_names", "xrefs_found") else "names"] = bad[:MOST_HANDLES]
        for extra in ("clause", "advice"):
            if check.get(extra) and state == FAIL:
                row[extra] = check[extra]
        results.append(row)
    order = {state: i for i, state in enumerate(STATES)}
    rank = {severity: i for i, severity in enumerate(SEVERITIES)}
    results.sort(key=lambda r: (order[r["state"]], rank[r["severity"]]))
    counts = {state: sum(1 for r in results if r["state"] == state) for state in (PASS, FAIL, NO_DATA, NOT_RUN)}
    return {
        "checklist": name,
        "verdict": verdict_of(counts),
        "coverage": coverage(counts),
        "counts": counts,
        "pass_means": PASS_MEANS,
        "checks_used": [{"id": r["id"], "label": r["label"], "from": r["from"]} for r in results],
        "results": results,
        "how_to_see": "Pass a result's handles to autocad_show to put the failing objects on screen.",
    }
