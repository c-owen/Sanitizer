"""Restore — substitute originals back from the key (FR-7, PG4).

Host-independent. Placeholders absent from the returned text are simply skipped,
with no error. Phase 1 does exact placeholder matching; markdown-robust matching
(lightly edited tokens) arrives in Phase 3.
"""

from __future__ import annotations

import re

from sanitizer_core.model import Key


def restore(text: str, key: Key) -> str:
    """Replace every known placeholder in ``text`` with its original value.

    Guarantees: each placeholder present is replaced by exactly its recorded
    original; placeholders not present are skipped silently (FR-7); replacement
    is a single pass, so an original that happens to contain a placeholder-like
    substring is never re-expanded.
    """
    entries = key.entries
    if not entries:
        return text
    # Longest first so one placeholder can't be shadowed by another's prefix.
    placeholders = sorted(entries, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(p) for p in placeholders))
    return pattern.sub(lambda match: entries[match.group()], text)
