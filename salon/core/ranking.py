# SPDX-License-Identifier: GPL-3.0-or-later
"""Search scoring. Pure — no gi, no fuzzy-matching library (see brief §6.6).

Two match kinds: substring (anywhere in the title) and initialism (query
letters match the first letter of consecutive significant words, e.g. "gfn"
matches "GeForce NOW"). Scores are only meaningful relative to each other
for a single query — sort descending and drop non-matches (score 0.0).
"""

from __future__ import annotations

import re

# Tokenizes on both whitespace/punctuation *and* camelCase boundaries, so
# "GeForce NOW" yields ["Ge", "Force", "NOW"] (initials "gfn") rather than
# ["geforce", "now"] (initials "gn") — the brief's own worked example.
_TOKEN_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|[0-9]+")

# Score bands, highest first: exact title match, prefix match, initialism,
# substring elsewhere in the title. Kept coarse and simple by design —
# there is no fuzzy edit-distance layer here.
_SCORE_EXACT = 100.0
_SCORE_PREFIX = 80.0
_SCORE_INITIALISM = 60.0
_SCORE_SUBSTRING = 40.0


def _words(title: str) -> list[str]:
    return [w.lower() for w in _TOKEN_RE.findall(title)]


def _initials(words: list[str]) -> str:
    return "".join(w[0] for w in words)


def score(query: str, title: str) -> float:
    """Score how well title matches query. 0.0 means no match at all."""
    q = query.strip().lower()
    if not q:
        return 0.0
    t = title.lower()

    if t == q:
        return _SCORE_EXACT
    if t.startswith(q):
        return _SCORE_PREFIX

    words = _words(title)
    if words and _initials(words).startswith(q):
        return _SCORE_INITIALISM

    if q in t:
        return _SCORE_SUBSTRING

    return 0.0


def rank_best(query: str, items: list[tuple[str, str]], limit: int) -> list[str]:
    """`rank`, deduplicated and capped.

    The same three lines were written out at both call sites — the
    television's search screen and, once the phone could search too, the
    remote — and they have to agree, because a result list that ranks
    differently depending on which screen you are looking at is a result
    list nobody can learn. Duplicates are real: a tile for an application
    that is also installed appears in both groups, and the catalogue copy
    is passed first precisely so that it is the one kept.
    """
    seen: set[str] = set()
    best: list[str] = []
    for item_id in rank(query, items):
        if item_id in seen:
            continue
        seen.add(item_id)
        best.append(item_id)
        if len(best) >= limit:
            break
    return best


def rank(query: str, items: list[tuple[str, str]]) -> list[str]:
    """Rank (id, title) pairs against query, best first. Ties keep input
    order (Python's sort is stable), which is how callers give catalogue
    entries priority over e.g. installed-app entries: pass catalogue items
    first."""
    scored = [(score(query, title), item_id) for item_id, title in items]
    scored = [(s, item_id) for s, item_id in scored if s > 0.0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item_id for _, item_id in scored]
