"""Cloak's own declared-terms store — the growable, in-window declared list (US2).

Declared terms have two homes. Buzz's plugin config holds the terms the user typed
in settings; Cloak **cannot write** that (there is no host API for it, and Cloak
never modifies Buzz). So terms the user adds *from the review window* — "add to my
list" when catching a miss (FR-16) or via the in-window list editor — live here
instead, in Cloak's own data directory next to the sidecars.

The pipeline **unions** this store with the config terms when it builds detectors,
so an added term takes effect on the **next** transcript, not just the current one
(that is what makes "add to my list" a real cross-transcript declared term rather
than a one-off redaction).

Entries are raw lines in the same tiny language the config textarea uses — a bare
``Karen`` or a categorized ``person: Jane`` (see
:func:`cloak_core.detectors.declared.parse_declared_terms`). Storage is a JSON list
of those lines; dedupe is by the term portion, case- and whitespace-insensitive, so
the same name is never declared twice. Pure filesystem + JSON; the directory is
**injected by the host**, exactly like :mod:`cloak_core.persistence`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DECLARED_FILE = "declared_terms.json"


def _term_of(line: str) -> str:
    """The term portion of a ``category: term`` (or bare ``term``) line."""
    line = line.strip()
    if ":" in line:
        return line.split(":", 1)[1].strip()
    return line


def _canonical(line: str) -> str:
    """Identity for a stored line: its term, whitespace-collapsed and casefolded."""
    return re.sub(r"\s+", " ", _term_of(line)).strip().casefold()


def read_declared_terms(directory: str | Path) -> list[str]:
    """Load the stored declared-term lines; ``[]`` if absent/unreadable."""
    path = Path(directory) / DECLARED_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(line) for line in data if str(line).strip()]


def write_declared_terms(directory: str | Path, terms: list[str]) -> None:
    """Overwrite the store with ``terms`` (created if needed), blanks dropped."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    cleaned = [line.strip() for line in terms if line.strip()]
    (path / DECLARED_FILE).write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_declared_term(directory: str | Path, term: str) -> list[str]:
    """Add ``term`` (if not already present) and persist; return the new list.

    Idempotent: a term already present (by canonical identity, ignoring category
    and case) is left untouched, so repeated "add to my list" never duplicates.
    """
    term = term.strip()
    terms = read_declared_terms(directory)
    if term and _canonical(term) not in {_canonical(t) for t in terms}:
        terms.append(term)
        write_declared_terms(directory, terms)
    return terms


def remove_declared_term(directory: str | Path, term: str) -> list[str]:
    """Remove every line matching ``term`` (by canonical identity); persist."""
    target = _canonical(term)
    terms = [t for t in read_declared_terms(directory) if _canonical(t) != target]
    write_declared_terms(directory, terms)
    return terms
