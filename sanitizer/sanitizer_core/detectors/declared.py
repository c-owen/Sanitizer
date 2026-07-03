"""Declared-list detection: the highest-trust tier (FR-1).

Detects every occurrence of a user-declared term, including case, possessive
and internal-whitespace variants, without corrupting substrings ("Jane" must
never match inside "Janet").

Terms may be **categorized** so the placeholder reads well: pass a
``dict[category, list[str]]`` (``{"person": ["Jane"], "project": ["Apollo"]}``)
to get ``{{PERSON-A}}`` / ``{{PROJECT-A}}``; a bare ``list[str]`` is uncategorized
and uses the generic ``{{TERM-1}}``.
"""

from __future__ import annotations

import re

from sanitizer_core.categories import label_for
from sanitizer_core.model import Detection, Span, TrustTier

_TYPE = "term"
_LABEL = "TERM"
_REASON = "matched your list"


def parse_declared_terms(raw: str) -> dict[str, list[str]]:
    """Parse a user's declared-terms text into ``{category: [term, ...]}``.

    One term per line; ``category: term`` sets a category (``person``, ``project``,
    …), a bare line falls back to the generic ``term`` category. Blank lines are
    ignored. Shared by the config pipeline and the demo surfaces so they parse
    identically.
    """
    by_category: dict[str, list[str]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            category, term = line.split(":", 1)
            category, term = category.strip().lower(), term.strip()
        else:
            category, term = "term", line
        if term:
            by_category.setdefault(category, []).append(term)
    return by_category


def _canonical(term: str) -> str:
    """Identity for a term: internal whitespace collapsed, casefolded."""
    return re.sub(r"\s+", " ", term).strip().casefold()


def _term_pattern(term: str) -> str:
    """A regex matching the term as a standalone token, tolerant of the
    whitespace between its words and anchored on word boundaries (substring
    safety). Returns ``""`` for a whitespace-only term."""
    tokens = [re.escape(tok) for tok in term.split()]
    if not tokens:
        return ""
    body = r"\s+".join(tokens)
    return rf"\b{body}\b"


class DeclaredListDetector:
    """Detects user-declared terms (FR-1).

    Assumes: ``text`` is the text spans index into.
    Guarantees: every occurrence of every declared term is returned exactly once
    (non-overlapping, longest-term-wins), word-boundary anchored, each Detection
    restores to the user's declared spelling, and its label reflects the term's
    category (or ``TERM`` when uncategorized).
    """

    def __init__(self, terms: list[str] | dict[str, list[str]]) -> None:
        pairs: list[tuple[str, str | None]] = []
        if isinstance(terms, dict):
            for category, items in terms.items():
                pairs.extend((term, category) for term in items)
        else:
            pairs.extend((term, None) for term in terms)

        # Keep the declared spelling (for restore) and category; dedupe by
        # canonical; drop blanks. Longest first so "Jane Doe" beats "Jane".
        self._entries: list[tuple[str, str | None]] = []
        seen: set[str] = set()
        for term, category in pairs:
            stripped = term.strip()
            canon = _canonical(stripped)
            if not canon or canon in seen:
                continue
            seen.add(canon)
            self._entries.append((stripped, category))
        self._entries.sort(key=lambda entry: len(entry[0]), reverse=True)
        self._regex = self._compile([term for term, _ in self._entries])

    @staticmethod
    def _compile(terms: list[str]) -> re.Pattern[str] | None:
        parts = [f"(?P<t{i}>{_term_pattern(t)})" for i, t in enumerate(terms)]
        if not parts:
            return None
        return re.compile("|".join(parts), re.IGNORECASE | re.UNICODE)

    def detect(self, text: str) -> list[Detection]:
        if self._regex is None:
            return []
        detections: list[Detection] = []
        for match in self._regex.finditer(text):
            term, category = self._entries[int(match.lastgroup[1:])]  # "t3" -> 3
            start, end = match.span()
            detections.append(
                Detection(
                    span=Span(start, end),
                    value=match.group(),
                    type=_TYPE if category is None else category,
                    label=_LABEL if category is None else label_for(category),
                    tier=TrustTier.DECLARED,
                    reason=_REASON,
                    canonical=_canonical(term),
                    restore=term,
                )
            )
        return detections
