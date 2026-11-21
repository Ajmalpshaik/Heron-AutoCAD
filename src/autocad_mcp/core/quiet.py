"""A quiet answer: counts and handles only (#44).

On 2026-11-09 an ``autocad_sequence`` of eight ``autocad_dimension_run`` steps
answered with about 15,000 characters: every dimension's points, text position
and measurement. The chat needed the counts and the handles. ``quiet=true`` on
the long-answer tools keeps exactly that:

- numbers, true / false and short words stay: the counts, ``completed``,
  ``mode``, a ``hint`` or a ``warning``;
- ``handle`` and ``handles`` stay whole, so the next call can use them;
- what failed stays, its first few entries, so the chat knows what to fix;
- every other list of objects goes, and ``left_out`` says how many of each
  there were. Their handles are kept as ``handles`` when the answer had none,
  and an object the call created keeps ``{"created": true, "handle": ...}``,
  so the gate's Keep or Discard still finds what to take back.

Pure data work: tested offline, and the same answer passed through twice
comes out the same.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

QUIET_FIELD = Field(
    description=(
        "True: answer with counts and handles only, without each object's points, sizes and "
        "measurements. For long runs and sequences, where the detail would fill the chat. "
        "What failed is still named. Default false."
    )
)

HANDLE_KEYS = ("handle", "handles")
FAILURE_KEYS = ("failed", "failures", "errors", "skipped_detail")
MOST_FAILURES = 5
# A list of plain values this short (layers made, a point) costs less than saying it was left out.
SHORT_LIST = 10
# A text answer longer than this, inside a quiet answer, is cut (an error never is).
MOST_TEXT = 300
LEFT_OUT = "left_out"


def quiet(result: Any) -> Any:
    """``result`` with counts and handles only. Anything but a dict comes back as it is."""
    if not isinstance(result, dict):
        return result
    kept: dict[str, Any] = {}
    left_out: dict[str, int] = dict(result.get(LEFT_OUT) or {}) if isinstance(result.get(LEFT_OUT), dict) else {}
    gathered: list[str] = []
    for key, value in result.items():
        if key == LEFT_OUT:
            continue
        if isinstance(value, dict):
            kept[key] = quiet(value)
        elif not isinstance(value, list):
            kept[key] = value
        elif key in HANDLE_KEYS:
            kept[key] = value
        elif key in FAILURE_KEYS:
            kept[key] = [quiet(item) for item in value[:MOST_FAILURES]]
            if len(value) > MOST_FAILURES:
                left_out[key] = max(left_out.get(key, 0), len(value))
        elif all(not isinstance(item, (dict, list)) for item in value) and len(value) <= SHORT_LIST:
            kept[key] = value
        else:
            created = [_stub(item) for item in value if _was_created(item)]
            gathered.extend(_handles_in(value))
            if created:
                kept[key] = created
            # max: a second pass sees only the stubs, and must not lower the count
            left_out[key] = max(left_out.get(key, 0), len(value))
    if gathered and not any(key in kept for key in HANDLE_KEYS):
        kept["handles"] = list(dict.fromkeys(gathered))
    if left_out:
        kept[LEFT_OUT] = left_out
    return kept


def quiet_text(text: Any) -> Any:
    """A step's text answer in a quiet sequence: an error whole, anything else cut short."""
    if not isinstance(text, str) or text.startswith("Error:") or len(text) <= MOST_TEXT:
        return text
    return f"{text[:MOST_TEXT]}... ({len(text) - MOST_TEXT} more characters left out: quiet)"


def _was_created(item: Any) -> bool:
    return isinstance(item, dict) and item.get("created") is True and isinstance(item.get("handle"), str)


def _stub(item: dict[str, Any]) -> dict[str, Any]:
    return {"created": True, "handle": item["handle"]}


def _handles_in(items: list[Any]) -> list[str]:
    found: list[str] = []
    for item in items:
        if isinstance(item, dict):
            if isinstance(item.get("handle"), str) and item["handle"]:
                found.append(item["handle"])
            if isinstance(item.get("handles"), list):
                found.extend(str(h) for h in item["handles"])
    return found
