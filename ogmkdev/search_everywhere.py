"""Search Everywhere and Quick Open: one query over files, symbols, actions and settings, ranked.

Matching is case-insensitive and fuzzy: the letters of the query must appear in the label in order.
A label that starts with the query ranks first, then one that contains it, then scattered matches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Candidate:
    category: str            # file | symbol | action | setting
    label: str
    detail: str
    target: Tuple             # what activating the candidate does (see the window)


def fuzzy_score(query: str, text: str) -> Optional[int]:
    """Higher is better; None when the query letters do not appear in order in ``text``."""
    if not query:
        return 0
    q = query.lower()
    t = text.lower()
    if t.startswith(q):
        return 1000 - len(t)
    if q in t:
        return 800 - t.index(q) - len(t) // 4
    position = 0
    gaps = 0
    previous = -1
    for char in q:
        found = t.find(char, position)
        if found < 0:
            return None
        if previous >= 0:
            gaps += found - previous - 1
        previous = found
        position = found + 1
    return max(1, 500 - gaps * 10 - len(t))


def rank(candidates: Iterable[Candidate], query: str, categories: Optional[Sequence[str]] = None,
         limit: int = 200) -> List[Candidate]:
    scored = []
    for candidate in candidates:
        if categories is not None and candidate.category not in categories:
            continue
        score = fuzzy_score(query, candidate.label)
        if score is not None:
            scored.append((-score, len(candidate.label), candidate.label, candidate))
    scored.sort(key=lambda item: item[:3])
    return [item[3] for item in scored[:limit]]
