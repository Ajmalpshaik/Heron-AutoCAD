"""Named check lists: the modeller's own sentences, run as checks (D-52).

The idea is Heron AI for Revit's QA checklists (its docs/50): each line the
modeller writes ("nothing on layer 0", "every title block filled in") becomes
a check from a fixed catalogue, run against the drawing, with PASS, FAIL or
NOT RUN, how many objects fail, which ones (so autocad_show can put them on
screen), and the severity, clause and advice the modeller gave it.

Everything here is pure: it judges data the tool gathered over COM, so every
rule is tested without AutoCAD.
"""

from __future__ import annotations

import re
from typing import Any

PASS, FAIL, NOT_RUN = "PASS", "FAIL", "NOT RUN"
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
        if key == "layer_names":
            try:
                re.compile(str(params["pattern"]))
            except re.error as exc:
                raise ValueError(f"Check {number}: the pattern does not read as a regular expression ({exc}).") from None
        if key == "text_heights":
            heights = params["heights"]
            if not isinstance(heights, list) or not heights or not all(isinstance(h, (int, float)) and h > 0 for h in heights):
                raise ValueError(f"Check {number}: 'heights' must be a list of positive numbers.")
        severity = str(given.get("severity", "medium")).lower()
        if severity not in SEVERITIES:
            raise ValueError(f"Check {number}: severity must be one of {', '.join(SEVERITIES)}.")
        clean.append({
            "check": key,
            "label": str(given.get("label") or CATALOGUE[key]["means"]),
            "params": params,
            "severity": severity,
            "clause": str(given.get("clause", "")),
            "advice": str(given.get("advice", "")),
        })  # fmt: skip
    return clean


def needs(checks: list[dict[str, Any]]) -> set[str]:
    """What the tool must read from the drawing for these checks."""
    wanted = {"layers"}
    for check in checks:
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
            return NOT_RUN, [], "the xrefs could not be read"
        return (FAIL if broken else PASS), list(broken), "xref names"
    if key == "title_block_filled":
        pattern = block_pattern(str(params["block"]))
        blocks = [b for b in data.get("blocks", []) if pattern.match(str(b.get("name", "")))]
        if not blocks:
            return NOT_RUN, [], f"no block named {params['block']} is in the drawing"
        bad = [b["handle"] for b in blocks if not b.get("attributes") or any(not str(v).strip() for v in b["attributes"].values())]
        return (FAIL if bad else PASS), bad, f"{len(blocks)} title block(s) read"
    if entities is None:
        return NOT_RUN, [], "the objects could not be read"
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
        bad = [e["handle"] for e in entities if e.get("height") is not None
               and not any(abs(float(e["height"]) - h) <= 1e-3 * max(h, 1) for h in allowed)]  # fmt: skip
    else:  # pragma: no cover - validate() refuses anything else
        return NOT_RUN, [], "unknown check"
    return (FAIL if bad else PASS), bad, f"{len(entities)} object(s) read"


def run(name: str, checks: list[dict[str, Any]], data: dict[str, Any]) -> dict[str, Any]:
    """Every check's result, worst first, and a one-line verdict."""
    results = []
    for check in checks:
        state, bad, note = _failing(check, data)
        row = {
            "check": check["check"],
            "label": check["label"],
            "state": state,
            "severity": check["severity"],
            "failing": len(bad),
            "note": note,
        }
        if bad:
            row["handles" if check["check"] not in ("layer_names", "xrefs_found") else "names"] = bad[:MOST_HANDLES]
        for extra in ("clause", "advice"):
            if check.get(extra) and state == FAIL:
                row[extra] = check[extra]
        results.append(row)
    order = {FAIL: 0, NOT_RUN: 1, PASS: 2}
    rank = {severity: i for i, severity in enumerate(SEVERITIES)}
    results.sort(key=lambda r: (order[r["state"]], rank[r["severity"]]))
    counts = {state: sum(1 for r in results if r["state"] == state) for state in (PASS, FAIL, NOT_RUN)}
    verdict = "PASS" if counts[FAIL] == 0 and counts[NOT_RUN] == 0 else ("FAIL" if counts[FAIL] else "NOT RUN")
    return {"checklist": name, "verdict": verdict, "counts": counts, "results": results,
            "how_to_see": "Pass a result's handles to autocad_show to put the failing objects on screen."}  # fmt: skip
