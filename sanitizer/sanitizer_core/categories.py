"""Category → placeholder-label mapping, shared by detectors.

A declared term or a model suggestion carries a *category*; the placeholder
label is the prefix the LLM sees. Semantic labels ("PERSON-A told PERSON-B about
PROJECT-A") read far better than opaque ones ("TERM-1 told TERM-2 …") — the
brief's usability goal (G3) and the "PERSON-A"-style glossary entry.

Entity categories render with **letters** (PERSON-A, PERSON-B …) so they read
like role labels; structured PII keeps **numbers** (EMAIL-1) since a transcript
may carry many. Uncategorized declared terms fall back to the generic ``TERM``.
"""

from __future__ import annotations

PERSON = "person"
ORG = "org"
PROJECT = "project"  # also covers programs / codenames
PLACE = "place"

# Category → placeholder label.
_LABELS = {
    PERSON: "PERSON",
    ORG: "ORG",
    PROJECT: "PROJECT",
    PLACE: "PLACE",
}

CATEGORIES: tuple[str, ...] = tuple(_LABELS)

# Labels that number with letters (A, B, …) rather than 1, 2, … .
ENTITY_LABELS = frozenset(_LABELS.values())


def label_for(category: str) -> str:
    """Return the placeholder label for ``category`` (uppercased if unknown)."""
    return _LABELS.get(category, category.upper())
