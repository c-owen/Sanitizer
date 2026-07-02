"""Placeholder schemes — the readable stand-ins shown for removed items.

A scheme must produce tokens that are unique per item and **robust** (FR-23):
markdown rendering, copy/paste and light editing must not split or alter them, so
restore stays reliable across the markdown round trip. Two properties matter:

* **markdown-safe** — no markdown-active characters, so a renderer can't format or
  swallow the token (``[[x]]`` becomes a wiki-link in some flavors; ``<x>`` an HTML
  tag; ``_x_`` italics — all unsafe);
* **ASCII-safe** — encodes cleanly to ASCII, so copy/paste through a legacy or
  ASCII-only app can't drop it (the Unicode ``⟦ ⟧`` brackets fail this — see the
  cp1252 console failure in DEV_NOTES).

The default :class:`BraceScheme` (``{{LABEL-N}}``) satisfies both. The interface
is swappable so the style can change without touching detection or substitution
(FR-14, OQ6); :class:`BracketScheme` (``⟦ ⟧``) remains available.
"""

from __future__ import annotations

from typing import Protocol

from sanitizer_core.categories import ENTITY_LABELS

# Characters with meaning in CommonMark / GFM inline or block syntax.
MARKDOWN_ACTIVE = frozenset("*_`[]()~#>!|\\<&")


def _to_letters(index: int) -> str:
    """1 → A, 26 → Z, 27 → AA … (bijective base-26, spreadsheet-style)."""
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _suffix(label: str, index: int, letter_labels: frozenset[str]) -> str:
    return _to_letters(index) if label in letter_labels else str(index)


def is_markdown_safe(token: str) -> bool:
    """True if ``token`` contains no markdown-active characters."""
    return not (set(token) & MARKDOWN_ACTIVE)


def is_ascii_safe(token: str) -> bool:
    """True if ``token`` encodes cleanly to ASCII (survives legacy copy/paste)."""
    try:
        token.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


class PlaceholderScheme(Protocol):
    """Formats a placeholder token for a labelled item index."""

    def format(self, label: str, index: int) -> str: ...


class BraceScheme:
    """``{{LABEL-N}}`` — ASCII-safe and markdown-safe (the default, FR-23).

    ``letter_labels`` render with letters (``{{PERSON-A}}``); all others number
    (``{{EMAIL-1}}``). Defaults to the entity labels (person/org/project/place).
    """

    OPEN = "{{"
    CLOSE = "}}"

    def __init__(self, letter_labels: frozenset[str] = ENTITY_LABELS) -> None:
        self.letter_labels = frozenset(letter_labels)

    def format(self, label: str, index: int) -> str:
        suffix = _suffix(label, index, self.letter_labels)
        return f"{self.OPEN}{label}-{suffix}{self.CLOSE}"


class BracketScheme:
    """``⟦LABEL-N⟧`` — markdown-safe but NOT ASCII-safe. Kept for callers that
    prefer the look and control their own UTF-8 sinks."""

    OPEN = "⟦"  # ⟦ MATHEMATICAL LEFT WHITE SQUARE BRACKET
    CLOSE = "⟧"  # ⟧ MATHEMATICAL RIGHT WHITE SQUARE BRACKET

    def __init__(self, letter_labels: frozenset[str] = ENTITY_LABELS) -> None:
        self.letter_labels = frozenset(letter_labels)

    def format(self, label: str, index: int) -> str:
        suffix = _suffix(label, index, self.letter_labels)
        return f"{self.OPEN}{label}-{suffix}{self.CLOSE}"


DEFAULT_SCHEME: PlaceholderScheme = BraceScheme()
