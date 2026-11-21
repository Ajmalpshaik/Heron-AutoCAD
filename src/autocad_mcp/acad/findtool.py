"""Searching the toolbox in plain words.

A hundred tools are only useful if the right one surfaces from the words a
draftsman would actually say - "how many metres of pipe on this layer", not
"invoke the length aggregation tool". This scores every tool against a phrase
and puts the best first.

It is deliberately small and pure: no AutoCAD, no index, no third-party
search engine. Scoring a phrase against a hundred short documents is fast
enough that the whole catalogue is searched on every call, which means there
is no index to go stale.

The scoring is bag-of-words with three ideas:

* **Where a word appears matters.** A word in the tool's own name is worth
  more than the same word in its summary, which is worth more than one in a
  "Use when" line.
* **A rare word tells you more than a common one.** "flange" appears in one
  tool, "layer" in thirty, so matching "flange" should count far more. That
  is inverse document frequency, worked out from the catalogue itself.
* **"Don't use when" counts against.** A tool that names itself only to send
  you elsewhere should not win on that mention.

And one rule on top (D-67, the idea of Heron AI for Revit's question mode):
**a plain question never gets a tool that changes the drawing first.** "How
many diffusers on this floor" wants a count, not a block inserted; ``rank``
puts the tools that only read ahead of everything else when the phrase reads
as a question.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field

# Words too common in a drawing office to tell two tools apart.
STOP_WORDS = frozenset("""
a an and are as at be been but by can do does for from get give got has have
how i if in into is it its just like make makes me my need needs not of on
one only or our out so some that the their them then there these they this
those to up use used uses using want was what when where which who will with
would you your drawing autocad tool call tools
""".split())

# What a modeller says on the left, what the catalogue says on the right.
# Only words a search would otherwise miss entirely.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "qty": ("count", "quantity"),
    "quantity": ("count", "take-off"),
    "takeoff": ("take-off", "count", "total"),
    "bom": ("schedule", "table", "count"),
    "schedule": ("table", "attributes"),
    "clash": ("interference", "collision"),
    "collision": ("interference", "clash"),
    "dim": ("dimension",),
    "dims": ("dimension",),
    "dimensions": ("dimension",),
    "tag": ("attribute", "label"),
    "tags": ("attribute", "label"),
    "titleblock": ("title", "block"),
    "sheet": ("layout", "paper"),
    "sheets": ("layout", "paper"),
    "plot": ("export", "pdf", "paper"),
    "print": ("export", "pdf", "plot"),
    "pdf": ("export", "plot"),
    "viewport": ("viewport", "layout", "scale"),
    "metres": ("length", "total"),
    "meters": ("length", "total"),
    "mm": ("units", "millimetres"),
    "unfold": ("development", "flat", "pattern"),
    "unroll": ("development", "flat", "pattern"),
    "flatten": ("flat", "development", "flatten"),
    "reducer": ("cone", "development", "transition"),
    "hole": ("bore", "hollow", "subtract"),
    "holes": ("bore", "bolt", "subtract"),
    "weight": ("volume", "mass", "properties"),
    "mass": ("volume", "properties"),
    "render": ("material", "visual", "style"),
    "texture": ("material",),
    "ucs": ("ucs", "coordinate", "rotated"),
    "rotated": ("ucs", "rotate", "twist"),
    "xref": ("import", "reference"),
    "purge": ("delete", "empty", "tidy"),
    "ifc": ("import", "remap", "layer"),
    "revit": ("import", "remap", "layer"),
    "bim": ("import", "remap", "layer"),
    "3d": ("solid", "3d"),
    "solid": ("solid", "3d"),
    "section": ("section", "slice", "cut"),
    "cut": ("slice", "section", "break"),
    "sweep": ("path", "along", "extrude"),
    "lisp": ("lisp", "autolisp"),
    "progn": ("sequence", "steps"),
    "batch": ("batch", "several", "many"),
    "steel": ("steel", "section"),
    "duct": ("duct", "hvac"),
    "pipe": ("pipe", "run"),
    "stair": ("stair", "riser"),
    "cctv": ("camera", "block"),
    "coordinates": ("coordinate", "point", "world", "convert"),
    "coordinate": ("point", "world", "convert"),
    "world": ("world", "coordinate", "convert"),
    "template": ("template", "import", "another"),
    "box": ("box", "solid"),
    "standard": ("standard", "check"),
    "standards": ("standard", "check"),
    "variable": ("variable", "sysvar"),
    "dimscale": ("dimscale", "variable", "scale"),
    "ltscale": ("ltscale", "variable", "scale"),
}

_WORD = re.compile(r"[a-z0-9][a-z0-9'-]*")

# Where a word appears. The name counts most, but not by much: "add", "draw",
# "set", "list" and "get" are in six to twelve tool names each, so they are
# the API's own verbs rather than anything about the job. Weighting the name
# too heavily let "set DIMSCALE" land on autocad_set_variable instead of
# autocad_drawing_setup. Dropping it from 6 to 3 fixed that without costing
# anything else. A "Don't use when" mention counts against the tool.
WEIGHT_NAME = 3.0
WEIGHT_TITLE = 3.0
WEIGHT_SUMMARY = 2.0
WEIGHT_USE_WHEN = 1.0
WEIGHT_AVOID = -1.5

# How hard rarity bites. At 1.0 a common word anywhere counts as much as a
# rare one, which is wrong: "layer" is in thirty tools and narrows nothing,
# while "DIMSCALE" is in three and all but names the tool.
#
# Both numbers were chosen by measuring, not taste: a sweep of name weight
# 1-6 against rarity power 1.5-3 over the 55 phrases in
# tests/test_find_tool.py. 3.0 and 1.5 gave the best result (45 of 55 first,
# 55 of 55 in the top three), and everything nearby scored almost the same,
# so the setting is a plateau rather than a knife edge. The phrases are our
# own, so read the score as a floor on a sample, not a promise.
RARITY_POWER = 1.5

# What a word we guessed is worth next to a word the user actually typed.
# Plurals and synonyms widen the net - "style" has to reach
# autocad_create_styles - but a guess should never outweigh the real word.
# Swept 0.3 to 0.7 over the 67 phrases in tests/test_find_tool.py: 54-55 of
# them put the right tool first and all 67 found it in the top three, so the
# exact value barely matters. Undiscounted it was 51 and 67; with no widening
# at all, 55 and 66.
EXPANSION_DISCOUNT = 0.6


def words(text: str) -> list[str]:
    """The searchable words of a phrase: lower case, no punctuation, no filler."""
    found = _WORD.findall(text.lower().replace("_", " "))
    return [w for w in found if w not in STOP_WORDS and len(w) > 1]


def plurals(word: str) -> tuple[str, ...]:
    """A word and its other number, so "style" finds autocad_create_styles.

    Only the query is widened, never the catalogue: that way a word's rarity is
    still measured on what the tools actually say, and one spelling in a phrase
    cannot change how much another word is worth.

    Deliberately crude - no stemmer. "-ies" and a plain "-s" cover the words a
    drawing office uses (style/styles, layer/layers, entity/entities) without
    mangling "gas" into "ga".
    """
    if word.endswith("ies") and len(word) > 4:
        return (word, word[:-3] + "y")
    if word.endswith("ss") or len(word) < 4:
        return (word,)
    if word.endswith("s"):
        return (word, word[:-1])
    return (word, word + "s", word + "es")


def expand(terms: list[str]) -> dict[str, float]:
    """The search words and the words they imply, each with how much it counts.

    A word the user typed is evidence. A word we guessed from it - the other
    number, or a synonym - is weaker evidence, so it counts for less. Without
    that discount, widening the query to catch "style" / "styles" cost four
    first places out of sixty-seven: the guessed forms were drowning the typed
    ones.
    """
    out: dict[str, float] = {}

    def offer(word: str, weight: float) -> None:
        if out.get(word, 0.0) < weight:
            out[word] = weight

    for term in terms:
        offer(term, 1.0)
        for form in plurals(term)[1:]:
            offer(form, EXPANSION_DISCOUNT)
        for synonym in SYNONYMS.get(term, ()):
            for form in plurals(synonym):
                offer(form, EXPANSION_DISCOUNT)
    return out


@dataclass(frozen=True)
class Entry:
    """One tool, as the search sees it."""

    tool: str
    title: str = ""
    summary: str = ""
    use_when: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()

    def fields(self) -> tuple[tuple[float, list[str]], ...]:
        return (
            (WEIGHT_NAME, words(self.tool)),
            (WEIGHT_TITLE, words(self.title)),
            (WEIGHT_SUMMARY, words(self.summary)),
            (WEIGHT_USE_WHEN, words(" ".join(self.use_when))),
            (WEIGHT_AVOID, words(" ".join(self.avoid))),
        )


@dataclass(frozen=True)
class Hit:
    tool: str
    score: float
    matched: tuple[str, ...] = field(default=())


def split_bullets(bullets: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """"Use when" lines and "Don't use when" lines, kept apart.

    They have to be scored differently: a tool that mentions a word only to
    point at a better tool should not win the search on that word.
    """
    use, avoid = [], []
    for line in bullets:
        (avoid if line.strip().lower().startswith("don't use when") else use).append(line)
    return tuple(use), tuple(avoid)


def rarity(entries: list[Entry]) -> dict[str, float]:
    """How much each word is worth: rare words tell you more than common ones.

    Plain inverse document frequency over the catalogue. "flange" is in one
    tool and "layer" in thirty, so a flange match must count for much more.
    """
    seen: dict[str, int] = {}
    for entry in entries:
        here = {w for _, bag in entry.fields() for w in bag}
        for word in here:
            seen[word] = seen.get(word, 0) + 1
    total = max(len(entries), 1)
    return {word: math.log(1.0 + total / count) for word, count in seen.items()}


def score(entry: Entry, terms: dict[str, float], weights: dict[str, float]) -> Hit:
    """How well one tool answers one phrase."""
    total = 0.0
    matched: list[str] = []
    for weight, bag in entry.fields():
        if not bag:
            continue
        for word in terms.keys() & set(bag):
            total += weight * terms[word] * weights.get(word, 1.0) ** RARITY_POWER
            if weight > 0.0:
                matched.append(word)
    return Hit(entry.tool, round(total, 6), tuple(sorted(set(matched))))


def search(entries: list[Entry], phrase: str, limit: int = 5) -> list[Hit]:
    """The best tools for a phrase, best first.

    Ties break on the tool's name, so the same phrase always gives the same
    answer - a search that reshuffles on equal scores is worse than useless
    when you are trying to work out why it missed.
    """
    terms = expand(words(phrase))
    if not terms:
        return []
    weights = rarity(entries)
    hits = [score(entry, terms, weights) for entry in entries]
    hits = [h for h in hits if h.score > 0.0]
    hits.sort(key=lambda h: (-h.score, h.tool))
    return hits[:limit]


# How a plain question starts. Only openings that ask for a fact: "how do I",
# "can you" and "could you" ask for a job to be done, and "does it clash" is
# answered here by autocad_check_interference, which makes solids, so "does"
# and "do" are left out on purpose.
QUESTION_STARTS = (
    "how many", "how much", "how long", "how big", "how far", "how wide", "how high",
    "how tall", "how deep", "how thick", "how large",
    "what's", "whats", "which", "is there", "are there", "is it", "is this", "is that", "are these",
    "are those", "are they", "are all", "is the", "are the", "where is", "where are",
    "has this", "have we", "tell me", "list",
)  # fmt: skip


def is_question(phrase: str) -> bool:
    """True when the phrase asks for a fact rather than for a job to be done.

    Any "what ..." asks ("what layers are frozen", "what did you draw"), except
    "what if", which is a job in disguise.
    """
    text = " ".join(_WORD.findall(phrase.lower().replace("_", " ")))
    if text.startswith("what ") and not text.startswith("what if "):
        return True
    return any(text == start or text.startswith(start + " ") for start in QUESTION_STARTS)


def rank(
    entries: list[Entry], phrase: str, limit: int = 5, reads: Callable[[str], bool] | None = None
) -> list[Hit]:
    """``search``, except that for a question the tools that only read come first.

    ``reads`` says whether a tool only reads. Inside each group the score
    order stays as it was, so a question with a read tool to answer it gets
    that tool first, and a change tool only after every read tool that matched.
    """
    hits = search(entries, phrase, limit=len(entries))
    if reads is not None and is_question(phrase):
        hits = [h for h in hits if reads(h.tool)] + [h for h in hits if not reads(h.tool)]
    return hits[:limit]
