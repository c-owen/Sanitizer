"""Transcript-level sanitization — per-segment, timing-preserving (Phase 5, PG5).

Runs the single-text :func:`~cloak_core.sanitizer.sanitize` over each segment with
one **shared** :class:`~cloak_core.vault.Vault`, so placeholders stay consistent
across the whole transcript while each segment's ``start``/``end`` is left
untouched (PG5). The per-segment decisions are merged into transcript-level
**review items** (one per distinct value, carrying every placement) — the unit the
review surface and the sidecar work with.

Host-independent: operates on plain segment-like inputs (anything with
``start``/``end``/``text``) and core types only — no buzz, no Qt.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from cloak_core.detectors.base import Detector
from cloak_core.detectors.declared import DeclaredListDetector
from cloak_core.model import (
    DecisionState,
    Detection,
    Key,
    TrustTier,
)
from cloak_core.placeholders import DEFAULT_SCHEME, PlaceholderScheme
from cloak_core.sanitizer import sanitize
from cloak_core.vault import Vault

_PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}")
# A "light" entity shape: capitalized runs (one or more Capitalized words). The
# inter-word gap is horizontal-only ([ \t]) so a run never spans a segment-join
# newline (which would invent a phrase present in no single segment).
_CAP_RUN_RE = re.compile(r"\b[A-Z][a-zA-Z]{2,}(?:[ \t]+[A-Z][a-zA-Z]{2,})*\b")


class SegmentLike(Protocol):
    """Structural input: a transcript segment with timing and text."""

    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Placement:
    """Where one occurrence sits: which segment, and the char span within it."""

    segment: int
    start: int
    end: int


@dataclass
class ReviewItem:
    """One distinct sensitive value across the whole transcript — a review row.

    ``placeholder`` is empty while a suggestion is still PENDING (it is allocated
    on approval, Phase 5b). ``placements`` lists every occurrence; ``count`` is how
    many. ``state`` drives whether the item is applied to the scrubbed text.
    """

    canonical: str
    placeholder: str
    original: str
    label: str
    type: str
    tier: TrustTier
    reason: str
    state: DecisionState
    placements: list[Placement] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.placements)


@dataclass
class SanitizedSegment:
    """One segment's original and scrubbed text, with its timing preserved."""

    start: int
    end: int
    original: str
    scrubbed: str


@dataclass
class TranscriptSanitization:
    """The outcome of sanitizing a whole transcript: scrubbed segments, the merged
    review items, the key, and whether verification passed."""

    segments: list[SanitizedSegment]
    items: list[ReviewItem]
    key: Key
    clean: bool = True
    survivors: list[Detection] = field(default_factory=list)

    @property
    def scrubbed_text(self) -> str:
        return "\n".join(segment.scrubbed for segment in self.segments)

    @property
    def original_text(self) -> str:
        return "\n".join(segment.original for segment in self.segments)

    @property
    def removed_items(self) -> int:
        return sum(1 for item in self.items if item.state == DecisionState.APPROVED)

    @property
    def pending_items(self) -> int:
        return sum(1 for item in self.items if item.state == DecisionState.PENDING)


def sanitize_transcript(
    segments: Sequence[SegmentLike],
    detectors: list[Detector],
    *,
    scheme: PlaceholderScheme = DEFAULT_SCHEME,
) -> TranscriptSanitization:
    """Sanitize every segment with one shared vault and merge the results.

    Guarantees: each segment's ``start``/``end`` is preserved (PG5); the same value
    gets the same placeholder across segments (shared vault); guaranteed tiers are
    auto-applied and suggestions held PENDING (FR-9); the merged ``clean`` is the
    AND of every segment's gate result (a leak anywhere fails the whole transcript).
    """
    vault = Vault(scheme)
    seg_results: list[SanitizedSegment] = []
    items_by_canonical: dict[str, ReviewItem] = {}
    order: list[str] = []
    clean = True
    survivors: list[Detection] = []

    for index, segment in enumerate(segments):
        text = segment.text or ""
        result = sanitize(text, detectors, vault=vault, scheme=scheme)
        seg_results.append(
            SanitizedSegment(segment.start, segment.end, text, result.scrubbed)
        )
        if not result.clean:
            clean = False
            survivors.extend(result.survivors)
        for decision in result.decisions:
            item = items_by_canonical.get(decision.canonical)
            if item is None:
                item = ReviewItem(
                    canonical=decision.canonical,
                    placeholder=decision.placeholder,
                    original=decision.original,
                    label=decision.label,
                    type=decision.type,
                    tier=decision.tier,
                    reason=decision.reason,
                    state=decision.state,
                )
                items_by_canonical[decision.canonical] = item
                order.append(decision.canonical)
            elif decision.tier.value < item.tier.value:
                # Defensive: a more-trusted tier for the same value wins the row.
                item.placeholder = decision.placeholder
                item.original = decision.original
                item.label = decision.label
                item.type = decision.type
                item.tier = decision.tier
                item.reason = decision.reason
                item.state = decision.state
            item.placements.extend(
                Placement(index, det.span.start, det.span.end)
                for det in decision.occurrences
            )

    items = [items_by_canonical[canonical] for canonical in order]
    return TranscriptSanitization(
        segments=seg_results,
        items=items,
        key=vault.key(),
        clean=clean,
        survivors=survivors,
    )


def apply_review(
    originals: Sequence[SanitizedSegment],
    items: Sequence[ReviewItem],
) -> tuple[list[SanitizedSegment], Key]:
    """Re-derive scrubbed segments + key from the items' current states (Phase 5b).

    Splices the placeholder of every APPROVED item at each of its placements into
    the matching original segment, right-to-left so spans stay valid. PENDING and
    REJECTED items are left in cleartext; an item still lacking a placeholder (an
    unapproved suggestion) is skipped. The returned key holds exactly the applied
    substitutions (PG8). This is the inverse used when the user edits decisions.
    """
    by_segment: dict[int, list[tuple[int, int, str]]] = {}
    entries: dict[str, str] = {}
    for item in items:
        if item.state != DecisionState.APPROVED or not item.placeholder:
            continue
        entries[item.placeholder] = item.original
        for placement in item.placements:
            by_segment.setdefault(placement.segment, []).append(
                (placement.start, placement.end, item.placeholder)
            )

    out: list[SanitizedSegment] = []
    for index, segment in enumerate(originals):
        scrubbed = segment.original
        for start, end, placeholder in sorted(
            by_segment.get(index, []), key=lambda r: r[0], reverse=True
        ):
            scrubbed = scrubbed[:start] + placeholder + scrubbed[end:]
        out.append(
            SanitizedSegment(segment.start, segment.end, segment.original, scrubbed)
        )
    return out, Key(entries)


def next_free_placeholder(
    existing: set[str],
    label: str,
    *,
    scheme: PlaceholderScheme = DEFAULT_SCHEME,
) -> str:
    """Return the first ``scheme`` placeholder for ``label`` not already in use.

    Used when the user approves a suggestion for the first time (Phase 5b): it gets
    a fresh, non-colliding placeholder while every already-assigned placeholder stays
    stable (so text the user already copied keeps the same tokens).
    """
    index = 1
    while True:
        candidate = scheme.format(label, index)
        if candidate not in existing:
            return candidate
        index += 1


# --- miss-catching (UX-3 / FR-22 / FR-16) -----------------------------------
@dataclass(frozen=True)
class MissCandidate:
    """An entity-shaped token still in cleartext that Cloak did NOT remove — a
    candidate for the user to confirm (never an "all clear"). Recall-only."""

    surface: str
    count: int


def _canonical(surface: str) -> str:
    return re.sub(r"\s+", " ", surface).strip().casefold()


def find_miss_candidates(
    text: str,
    *,
    known: frozenset[str] | set[str] = frozenset(),
    limit: int = 8,
) -> list[MissCandidate]:
    """Capitalized runs still present in ``text`` that aren't already flagged.

    A *light heuristic*, not a detector: it surfaces "candidates to confirm," to make
    catching a miss as cheap as approving a find (UX-3), and must never be read as a
    guarantee. Placeholders are ignored; any candidate whose casefold is in ``known``
    (already a declared/PII/suggested item) is skipped. Sorted by frequency, then name.
    """
    masked = _PLACEHOLDER_RE.sub(" ", text)
    seen: dict[str, list] = {}
    order: list[str] = []
    for match in _CAP_RUN_RE.finditer(masked):
        surface = match.group()
        canonical = _canonical(surface)
        if canonical in known:
            continue
        if canonical not in seen:
            seen[canonical] = [surface, 0]
            order.append(canonical)
        seen[canonical][1] += 1
    candidates = [MissCandidate(seen[c][0], seen[c][1]) for c in order]
    candidates.sort(key=lambda mc: (-mc.count, mc.surface.casefold()))
    return candidates[:limit]


def build_manual_item(
    surface: str,
    segments: Sequence[SanitizedSegment],
    *,
    existing_placeholders: set[str],
    label: str = "TERM",
) -> ReviewItem | None:
    """Build an APPROVED, declared-tier :class:`ReviewItem` that redacts ``surface``
    everywhere it occurs (word-boundary safe), or ``None`` if it never occurs.

    Used by the review UI's select-to-redact / miss-catching (FR-16): the user turns
    an un-removed token into a removal. Reuses the declared detector so the match is
    substring-safe, and allocates a fresh, non-colliding placeholder.
    """
    detector = DeclaredListDetector([surface])
    placements: list[Placement] = []
    canonical = _canonical(surface)
    original = surface.strip()
    for index, segment in enumerate(segments):
        for detection in detector.detect(segment.original):
            placements.append(
                Placement(index, detection.span.start, detection.span.end)
            )
            canonical = detection.canonical
            original = detection.restore
    if not placements:
        return None
    placeholder = next_free_placeholder(existing_placeholders, label)
    return ReviewItem(
        canonical=canonical,
        placeholder=placeholder,
        original=original,
        label=label,
        type="term",
        tier=TrustTier.DECLARED,
        reason="redacted by you",
        state=DecisionState.APPROVED,
        placements=placements,
    )


# --- on-demand model suggestions (windowed) ---------------------------------
def _suggestion_windows(
    segments: Sequence[SanitizedSegment], window_chars: int
) -> list[str]:
    """Join consecutive segments' *original* text into ~``window_chars`` blocks.

    A suggestion model needs sentence-sized context — running it on each caption
    fragment starves it (and is far slower). We give it windows instead; the spans
    it returns are discarded and each surface is re-located per segment below, so a
    phantom that a join might invent simply fails to locate and is dropped.
    """
    windows: list[str] = []
    buffer: list[str] = []
    size = 0
    for segment in segments:
        text = segment.original or ""
        buffer.append(text)
        size += len(text) + 1
        if size >= window_chars:
            windows.append(" ".join(buffer))
            buffer, size = [], 0
    if buffer:
        windows.append(" ".join(buffer))
    return windows


def _locate_placements(
    surface: str, segments: Sequence[SanitizedSegment]
) -> list[Placement]:
    """Every word-boundary-safe occurrence of ``surface`` across the segments."""
    detector = DeclaredListDetector([surface])
    placements: list[Placement] = []
    for index, segment in enumerate(segments):
        for detection in detector.detect(segment.original):
            placements.append(
                Placement(index, detection.span.start, detection.span.end)
            )
    return placements


def suggest_items(
    segments: Sequence[SanitizedSegment],
    detector: Detector,
    *,
    known_canonicals: frozenset[str] | set[str] = frozenset(),
    window_chars: int = 1200,
) -> list[ReviewItem]:
    """Run a suggestion ``detector`` over windowed transcript text → PENDING items.

    The model runs over joined windows (context, speed); each proposed surface is then
    **re-located precisely** in the segments (word-boundary safe), so every placement
    is an exact, splice-safe span regardless of the model's own offsets. Returns one
    :class:`ReviewItem` per distinct surface — ``SUGGESTED`` tier, ``PENDING`` state,
    empty placeholder (allocated on approval, like any suggestion) — deduped against
    ``known_canonicals`` (declared/PII/existing suggestions) and against itself.
    Surfaces that don't actually occur in any segment (join phantoms) are dropped.
    """
    proposals: dict[str, tuple[str, str, str, str]] = {}
    order: list[str] = []
    for window in _suggestion_windows(segments, window_chars):
        for detection in detector.detect(window):
            canonical = detection.canonical
            if canonical in known_canonicals or canonical in proposals:
                continue
            proposals[canonical] = (
                detection.restore or detection.value,
                detection.label,
                detection.type,
                detection.reason,
            )
            order.append(canonical)

    items: list[ReviewItem] = []
    for canonical in order:
        surface, label, type_, reason = proposals[canonical]
        placements = _locate_placements(surface, segments)
        if not placements:
            continue
        items.append(
            ReviewItem(
                canonical=canonical,
                placeholder="",
                original=surface,
                label=label,
                type=type_,
                tier=TrustTier.SUGGESTED,
                reason=reason,
                state=DecisionState.PENDING,
                placements=placements,
            )
        )
    return items


# --- JSON (de)serialization for the sidecar ---------------------------------
def segment_to_dict(segment: SanitizedSegment) -> dict:
    return {
        "start": segment.start,
        "end": segment.end,
        "original": segment.original,
        "scrubbed": segment.scrubbed,
    }


def segment_from_dict(data: dict) -> SanitizedSegment:
    return SanitizedSegment(
        start=data["start"],
        end=data["end"],
        original=data.get("original", ""),
        scrubbed=data.get("scrubbed", ""),
    )


def item_to_dict(item: ReviewItem) -> dict:
    return {
        "canonical": item.canonical,
        "placeholder": item.placeholder,
        "original": item.original,
        "label": item.label,
        "type": item.type,
        "tier": item.tier.name,
        "reason": item.reason,
        "state": item.state.value,
        "placements": [
            {"segment": p.segment, "start": p.start, "end": p.end}
            for p in item.placements
        ],
    }


def item_from_dict(data: dict) -> ReviewItem:
    return ReviewItem(
        canonical=data["canonical"],
        placeholder=data.get("placeholder", ""),
        original=data["original"],
        label=data["label"],
        type=data["type"],
        tier=TrustTier[data["tier"]],
        reason=data.get("reason", ""),
        state=DecisionState(data["state"]),
        placements=[
            Placement(p["segment"], p["start"], p["end"])
            for p in data.get("placements", [])
        ],
    )
