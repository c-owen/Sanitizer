"""Core domain model for Sanitizer — host-independent (no buzz, no Qt).

These types describe *what was detected* and *how it was replaced*, as plain
data with no dependency on Buzz, Qt or I/O — so the sanitization guarantees can
be tested in isolation (the brief's "verifiable independently" mandate).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class TrustTier(enum.IntEnum):
    """How much a detection is trusted — and thus whether it is removed
    automatically. Lower value == higher trust (wins overlap resolution).

    Glossary order: declared > pattern-detected PII > model-suggested.
    """

    DECLARED = 0  # the user's own list — authoritative, removed automatically
    PII = 1  # structured pattern match (phone, email, …) — Phase 2
    SUGGESTED = 2  # model proposal — review-gated, never auto-applied (Phase 4)


class DecisionState(enum.Enum):
    """The user-visible state of an item."""

    APPROVED = "approved"  # will be / was replaced by a placeholder
    REJECTED = "rejected"  # deliberately kept in cleartext (still shown)
    PENDING = "pending"  # awaiting review (suggestions; Phase 4)


@dataclass(frozen=True)
class Span:
    """A half-open character range ``[start, end)`` into a specific text."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"invalid span: ({self.start}, {self.end})")

    @property
    def length(self) -> int:
        return self.end - self.start

    def overlaps(self, other: Span) -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class Detection:
    """One occurrence of something sensitive found in a text.

    Assumes: ``span`` indexes the exact text the detector was given.
    Guarantees (by every detector): ``value == text[span.start:span.end]`` and
    ``span`` lies within the text. ``canonical`` is the identity used to group
    occurrences of the same thing (same canonical → same placeholder);
    ``restore`` is the value to substitute back (e.g. the declared spelling).
    """

    span: Span
    value: str  # the exact matched surface text
    type: str  # category for display/grouping/toggling, e.g. "term", "phone"
    label: str  # placeholder label, e.g. "TERM", "EMAIL" (self-described → FR-14)
    tier: TrustTier
    reason: str  # human-readable "why flagged"
    canonical: str  # normalized identity (e.g. casefolded)
    restore: str  # value to put back on restore
    score: float = 1.0  # model confidence in [0, 1]; 1.0 for exact/guaranteed hits


@dataclass
class Decision:
    """One item-level decision: a distinct sensitive value, its placeholder and
    every occurrence of it. The home surface of the review UI (Phase 5)."""

    canonical: str
    placeholder: str
    label: str
    original: str
    tier: TrustTier
    type: str
    reason: str
    state: DecisionState
    occurrences: list[Detection] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.occurrences)


@dataclass(frozen=True)
class Key:
    """The reversible map placeholder → original value. THE secret (PG8).

    Stored separately from the scrubbed text; never embedded in the output.
    """

    entries: dict[str, str] = field(default_factory=dict)

    def original_for(self, placeholder: str) -> str | None:
        return self.entries.get(placeholder)

    def to_dict(self) -> dict[str, str]:
        return dict(self.entries)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Key:
        return cls(entries=dict(data))


@dataclass
class SanitizationResult:
    """The outcome of sanitizing one text: the scrubbed text, the per-item
    decisions, the key, and whether it passed verification (Phase 2)."""

    scrubbed: str
    decisions: list[Decision]
    key: Key
    clean: bool = True
    survivors: list[Detection] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return len(self.decisions) == 0
